import frappe
from frappe.model.document import Document

class cuttingoperation(Document):
    SIZE_MAP = {
        'S':    'Small',
        'M':    'Medium',
        'L':    'Large',
        'XL':   'Extra Large',
        'XXL':  '2X Large',
        '2':    '2',
        '4':    '4',
        '6':    '6',
        '8':    '8',
        '14':   '14',
        '16':   '16',
    }

    def before_save(self):
        # Calculate total cost components (if you still need them)
        total_ws = total_worker = total_rolls = 0.0

        if self.workstation:
            ws = frappe.get_doc("Workstation", self.workstation)
            total_ws = ws.hour_rate * (self.total_hours or 0)

        for w in self.workers or []:
            total_worker += (w.cost_per_hour or 0) * (w.total_hours or 0)

        for u in self.used_rolls or []:
            if u.roll:
                rolls = frappe.get_doc("Rolls", u.roll)
                total_rolls += (u.used_qty or 0) * (rolls.price_per_kg or 0)

        self.used_rolls_cost = total_rolls
        self.individual_cost = 0.0
        self.total_cost = total_ws + total_worker + total_rolls

        # Propagate roll warehouse
        for u in self.used_rolls or []:
            if u.roll:
                u.roll_warehouse = frappe.db.get_value("Rolls", u.roll, "warehouse")

        # Build cutting_parts
        self.set('cutting_parts', [])
        variants = []
        for pb in self.parent_boms or []:
            if not pb.parent_bom: continue
            for item in frappe.get_doc('BOM', pb.parent_bom).items or []:
                vs = frappe.get_all('Item',
                    filters={'variant_of': item.item_code, 'disabled': 0},
                    fields=['name'])
                variants += [v.name for v in vs]

        parts = []
        for u in self.used_rolls or []:
            lap = u.lap or 0
            color = (u.color or '').strip()
            if lap <= 0 or not color: continue

            for sm in self.size_matrix or []:
                raw = (sm.size or '').strip()
                size_val = self.SIZE_MAP.get(raw, raw)
                qty_per = sm.qty or 0
                qty = lap * qty_per
                if qty <= 0: continue

                for v in variants:
                    attrs = frappe.get_all('Item Variant Attribute',
                        filters={'parent': v},
                        fields=['attribute', 'attribute_value'])
                    amap = {a.attribute.strip().lower(): (a.attribute_value or '').strip()
                            for a in attrs}
                    if amap.get('colour') == color and amap.get('size') == str(size_val):
                        parts.append({
                            'variant': v,
                            'quantity': qty,
                            'roll_relation': u.roll
                        })

        for p in parts:
            cp = self.append('cutting_parts', {})
            cp.part           = p['variant']
            cp.quantity       = p['quantity']
            cp.warehouse      = self.distination_warehouse
            cp.roll_relation  = p['roll_relation']

    def on_submit(self):
        if not self.used_rolls:
            return

        company = frappe.defaults.get_user_default("Company")

        # 1) Material Issue for raw rolls
        issue = frappe.new_doc("Stock Entry")
        issue.purpose = issue.stock_entry_type = "Material Issue"
        issue.company = company

        for u in self.used_rolls:
            if not u.roll or (u.used_qty or 0) <= 0:
                continue
            r = frappe.get_doc("Rolls", u.roll)
            issue.append("items", {
                "item_code": r.fabric_item,
                "qty": u.used_qty,
                "uom": frappe.db.get_value("Item", r.fabric_item, "stock_uom"),
                "s_warehouse": u.roll_warehouse
            })

        if issue.items:
            issue.insert()
            issue.submit()
            self.db_set("stock_entry_name", issue.name)

            # adjust roll weight & log used_time
            for u in self.used_rolls:
                if not u.roll: continue
                r = frappe.get_doc("Rolls", u.roll)
                used = u.used_qty or 0
                r.weight = (r.weight or 0) - used
                ute = r.append("used_time", {})
                ute.operation    = self.name
                ute.weight_used  = used
                r.save()

        # 2) Material Receipt for cut parts into batches
        receipt = frappe.new_doc("Stock Entry")
        receipt.purpose = receipt.stock_entry_type = "Material Receipt"
        receipt.company = company

        for cp in self.cutting_parts:
            if not cp.part or (cp.quantity or 0) <= 0:
                continue

            # generate or fetch batch
            batch_id = f"{cp.roll_relation}-{self.name}-{cp.part}"
            if not frappe.db.exists("Batch", batch_id):
                frappe.get_doc({
                    "doctype": "Batch",
                    "batch_id": batch_id,
                    "item": cp.part,
                    "batch_qty": cp.quantity
                }).insert()

            receipt.append("items", {
                "item_code": cp.part,
                "batch_no": batch_id,
                "qty": cp.quantity,
                "uom": frappe.db.get_value("Item", cp.part, "stock_uom"),
                "t_warehouse": cp.warehouse
            })

        if receipt.items:
            receipt.insert()
            receipt.submit()
            self.db_set("receipt_entry_name", receipt.name)

    def on_cancel(self):
        # 1) Cancel stock entries
        for field in ("stock_entry_name", "receipt_entry_name"):
            name = self.get(field)
            if name:
                try:
                    frappe.get_doc("Stock Entry", name).cancel()
                except frappe.DoesNotExistError:
                    pass

        # 2) Revert roll weights & cleanup used_time
        for u in self.used_rolls or []:
            if not u.roll: continue
            r = frappe.get_doc("Rolls", u.roll)
            used = u.used_qty or 0
            r.weight = (r.weight or 0) + used
            for ut in list(r.used_time or []):
                if ut.operation == self.name:
                    r.remove(ut)
            r.save()

        # 3) Delete created batches
        for cp in self.cutting_parts or []:
            bid = f"{cp.roll_relation}-{self.name}-{cp.part}"
            if frappe.db.exists("Batch", bid):
                frappe.delete_doc("Batch", bid, force=True)
