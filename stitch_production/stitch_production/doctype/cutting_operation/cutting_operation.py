import frappe
from frappe.model.document import Document
from frappe import _

class cuttingoperation(Document):

    SIZE_MAP = {
        'S': 'Small',
        'M': 'Medium',
        'L': 'Large',
        'XL': 'Extra Large',
        'XXL': '2X Large'
    }

    def before_save(self):
        # 0. Fetch roll_warehouse from linked Rolls
        for ur in (self.used_rolls or []):
            if ur.roll:
                roll_doc = frappe.get_doc("Rolls", ur.roll)
                ur.roll_warehouse = roll_doc.warehouse

        # 1. Clear previous parts
        self.set('cutting_parts', [])

        # 2. Collect all raw material variants from parent BOMs
        raw_material_variants = []
        for pb in (self.parent_boms or []):
            if not pb.parent_bom:
                continue
            bom_doc = frappe.get_doc('BOM', pb.parent_bom)
            for bi in (bom_doc.items or []):
                template_code = bi.item_code
                variants = frappe.get_all(
                    'Item',
                    filters={'variant_of': template_code, 'disabled': 0},
                    fields=['name']
                )
                for v in variants:
                    raw_material_variants.append(v.name)

        # 3. Compute quantities for each matching variant
        parts_qty_list = []
        for ur in (self.used_rolls or []):
            lap = ur.lap or 0
            roll_color = (ur.color or '').strip()
            if lap <= 0 or not roll_color:
                continue

            for sm in (self.size_matrix or []):
                raw_size = (sm.size or '').strip()
                size_value = self.SIZE_MAP.get(raw_size, raw_size)
                qty_per_size = sm.qty or 0
                total_qty = lap * qty_per_size
                if total_qty <= 0:
                    continue

                for variant_code in raw_material_variants:
                    attrs = frappe.get_all(
                        'Item Variant Attribute',
                        filters={'parent': variant_code},
                        fields=['attribute', 'attribute_value']
                    )
                    attr_map = {
                        a.attribute.strip().lower(): (a.attribute_value or '').strip()
                        for a in attrs
                    }
                    color_val = attr_map.get('colour')
                    size_val = attr_map.get('size')

                    if color_val == roll_color and size_val == size_value:
                        parts_qty_list.append({
                            'variant': variant_code,
                            'quantity': total_qty
                        })

        # 4. Append results to cutting_parts
        for p in parts_qty_list:
            cp = self.append('cutting_parts', {})
            cp.part = p['variant']
            cp.quantity = p['quantity']

    def on_submit(self):
        # Create Stock Entry to issue fabric from used rolls
        if not self.used_rolls:
            return

        stock_entry = frappe.new_doc("Stock Entry")
        stock_entry.purpose = "Material Issue"
        stock_entry.stock_entry_type = "Material Issue"
        stock_entry.company = frappe.defaults.get_user_default("Company")

        for ur in self.used_rolls:
            if not ur.roll:
                continue

            roll_doc = frappe.get_doc("Rolls", ur.roll)
            fabric_item = roll_doc.fabric_item
            warehouse = ur.roll_warehouse
            qty = ur.used_qty

            if not fabric_item or not warehouse or not qty or qty <= 0:
                continue

            stock_entry.append("items", {
                "item_code": fabric_item,
                "qty": qty,
                "uom": frappe.db.get_value("Item", fabric_item, "stock_uom"),
                "s_warehouse": warehouse
            })

        if stock_entry.items:
            stock_entry.insert()
            stock_entry.submit()
