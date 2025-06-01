import frappe
from frappe.model.document import Document
from frappe import _

class cuttingoperation(Document):
    SIZE_MAP = {
        'S': 'Small',
        'M': 'Medium',
        'L': 'Large',
        'XL': 'Extra Large',
        'XXL': '2X Large',
	    '2': '2',
	    '4': '4',
	    '6': '6',
	    '8': '8',
	    '14': '14',
	    '16': '16',
    }

    def before_save(self):
        total_ws = 0
        total_worker = 0
        total_rolls = 0
        total_cost = 0
        
        #workstation
        if self.workstation:
            ws = frappe.get_doc("Workstation", self.workstation)
            total_ws = ws.hour_rate * self.total_hours

        #worker
        for row in (self.workers or []):
            total_worker += row.cost_per_hour * row.total_hours

        #total rolls cost
        for rolls_cost in (self.used_rolls or []):
            doc = frappe.get_doc("Rolls", rolls_cost.roll)
            qty = rolls_cost.used_qty
            rate = doc.price_per_kg
            total_rolls += qty * rate
        
        self.used_rolls_cost = total_rolls

        #total cost
        self.individual_cost = 0.0
        total_cost += total_ws + self.individual_cost + total_worker + total_rolls
        self.total_cost = total_cost
        
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
                    color_val = (attr_map.get('colour') or '').strip()
                    size_val = (attr_map.get('size') or '').strip()

                    if color_val == roll_color and size_val == str(size_value):
                        parts_qty_list.append({
                            'variant': variant_code,
                            'quantity': total_qty,
                            'roll_relation': ur.roll
                        })

        # 4. Append results to cutting_parts
        for p in parts_qty_list:
            cp = self.append('cutting_parts', {})
            cp.part = p['variant']
            cp.quantity = p['quantity']
            cp.warehouse = self.distination_warehouse
            cp.roll_relation = p['roll_relation']

    def on_submit(self):
        if not self.used_rolls:
            return

        # 1. Create Stock Entry
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

            # 2. Update Rolls weight and append to used_time
            for ur in self.used_rolls:
                if not ur.roll:
                    continue

                roll_doc = frappe.get_doc("Rolls", ur.roll)
                used_qty = ur.used_qty or 0

                roll_doc.weight = (roll_doc.weight or 0) - used_qty

                used_time_entry = roll_doc.append("used_time", {})
                used_time_entry.operation = self.name
                used_time_entry.weight_used = used_qty

                roll_doc.save()
        
        self.db_set("stock_entry_name", stock_entry.name)

        # 3. Create Batches with proper batch_qty
        for part in self.cutting_parts:
            if not part.part or not part.roll_relation:
                continue

            batch_id = f"{part.roll_relation}-{self.name}-{part.part}"
            if not frappe.db.exists("Batch", batch_id):
                frappe.get_doc({
                    "doctype": "Batch",
                    "batch_id": batch_id,
                    "item": part.part,
                    "batch_qty": part.quantity
                }).insert()

    def on_cancel(self):
        # 1) Cancel the Stock Entry
        if self.stock_entry_name:
            try:
                se = frappe.get_doc("Stock Entry", self.stock_entry_name)
                se.cancel()
            except frappe.DoesNotExistError:
                frappe.log_error(f"Stock Entry {self.stock_entry_name} does not exist")
                pass

        # 2) Revert Rolls weight and remove used_time entries
        for ur in (self.used_rolls or []):
            if not ur.roll:
                continue

            roll = frappe.get_doc("Rolls", ur.roll)
            roll.weight = (roll.weight or 0) + (ur.used_qty or 0)
            # remove used_time entries for this operation
            for ut in list(roll.used_time or []):
                if ut.operation == self.name:
                    roll.remove(ut)
            roll.save()

        # 3) Delete Batches
        for cp in (self.cutting_parts or []):
            batch_id = f"{cp.roll_relation}-{self.name}-{cp.part}"
            if frappe.db.exists("Batch", batch_id):
                frappe.delete_doc("Batch", batch_id, force=True)

        # 4) Clear Cutting Parts table
        #self.db_set("cutting_parts", [])

