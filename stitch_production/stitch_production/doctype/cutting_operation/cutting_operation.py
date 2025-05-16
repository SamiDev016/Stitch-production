import frappe
from frappe.model.document import Document

class cuttingoperation(Document):

    # Map shorthand sizes to full attribute values
    SIZE_MAP = {
        'S': 'Small',
        'M': 'Medium',
        'L': 'Large',
        'XL': 'Extra Large',
        'XXL': '2X Large'
    }

    def before_save(self):
        # 1. Clear previous parts
        self.set('cutting_parts', [])

        # 2. Collect raw material variants
        raw_material_variants = []
        for pb in (self.parent_boms or []):
            if not pb.parent_bom:
                continue
            bom = frappe.get_doc('BOM', pb.parent_bom)
            for bi in (bom.items or []):
                for v in frappe.get_all('Item', filters={'variant_of': bi.item_code, 'disabled': 0}, fields=['name']):
                    raw_material_variants.append(v.name)

        # 3. Compute quantities and assign warehouse & roll code
        parts_qty = []
        for ur in (self.used_rolls or []):
            lap = ur.lap or 0
            color = (ur.color or '').strip()
            roll_code = ur.roll
            if lap <= 0 or not color or not roll_code:
                continue

            roll_wh = frappe.get_value('Rolls', roll_code, 'warehouse')

            for sm in (self.size_matrix or []):
                raw = (sm.size or '').strip()
                size = self.SIZE_MAP.get(raw, raw)
                total = lap * (sm.qty or 0)
                if total <= 0:
                    continue

                for variant in raw_material_variants:
                    attrs = frappe.get_all(
                        'Item Variant Attribute',
                        filters={'parent': variant},
                        fields=['attribute', 'attribute_value']
                    )
                    amap = {a.attribute.strip().lower(): (a.attribute_value or '').strip() for a in attrs}
                    if amap.get('colour') == color and amap.get('size') == size:
                        parts_qty.append({
                            'variant': variant,
                            'quantity': total,
                            'warehouse': roll_wh,
                            'roll': roll_code
                        })

        # 4. Populate cutting_parts
        for p in parts_qty:
            cp = self.append('cutting_parts', {})
            cp.part = p['variant']
            cp.quantity = p['quantity']
            cp.warehouse = p['warehouse']
            cp.roll = p['roll']  # store roll code for later use

    def on_submit(self):
        # 5. Consume rolls (issue stock of fabric_item)
        for ur in (self.used_rolls or []):
            lap = ur.lap or 0
            roll_code = ur.roll
            if lap <= 0 or not roll_code:
                continue
            fabric_item = frappe.get_value('Rolls', roll_code, 'fabric_item')
            from_wh = frappe.get_value('Rolls', roll_code, 'warehouse')
            se_issue = frappe.get_doc({
                'doctype': 'Stock Entry',
                'stock_entry_type': 'Material Issue',
                'from_warehouse': from_wh,
                'items': [{
                    'item_code': fabric_item,
                    'qty': lap,
                    'uom': frappe.get_value('Item', fabric_item, 'stock_uom')
                }]
            })
            se_issue.insert(ignore_permissions=True)

        # 6. Create batches and receive raw parts
        for cp in (self.cutting_parts or []):
            to_wh = cp.warehouse
            if not to_wh:
                frappe.throw(f"No target warehouse for part {cp.part}")
            batch_id = f"{self.name}-{cp.part}"
            frappe.get_doc({
                'doctype': 'Batch',
                'batch_id': batch_id,
                'item': cp.part
            }).insert(ignore_permissions=True)
            se_receipt = frappe.get_doc({
                'doctype': 'Stock Entry',
                'stock_entry_type': 'Material Receipt',
                'to_warehouse': to_wh,
                'items': [{
                    'item_code': cp.part,
                    'qty': cp.quantity,
                    'batch_no': batch_id,
                    'uom': frappe.get_value('Item', cp.part, 'stock_uom')
                }]
            })
            se_receipt.insert(ignore_permissions=True)
