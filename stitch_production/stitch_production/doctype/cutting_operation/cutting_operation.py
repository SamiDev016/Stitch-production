import frappe
from frappe.model.document import Document

class cuttingoperation(Document):
    SIZE_MAP = {
        'XS':     'XS',
        'S':    'S',
        'M':    'M',
        'L':    'L',
        'XL':   'XL',
        'XXL':  'XXL',
        'XXXL': 'XXXL',
        '6 ans':    '6',
        '8 ans':    '8',
        '10 ans':   '10',
        '12 ans':   '12',
        '14 ans':   '14',
        '16 ans':   '16',
    }
    def before_save(self):
        total_ws = total_rolls = 0.0
        total_sw = total_dw = total_cw = total_sew = 0.0

        # Calculate workstation cost
        if self.workstation:
            ws = frappe.get_doc("Workstation", self.workstation)
            total_ws = ws.hour_rate * (self.total_hours or 0)

        # Spreaders
        for w in self.spreading_workers or []:
            if not w.worker:
                continue
            emp = frappe.get_doc("Employee", w.worker)
            rate = (emp.ctc or 0) / 22 / 8
            total_sw += rate * (w.total_hours or 0)

        # Drawers
        for w in self.drawing_workers or []:
            if not w.worker:
                continue
            emp = frappe.get_doc("Employee", w.worker)
            rate = (emp.ctc or 0) / 22 / 8
            total_dw += rate * (w.total_hours or 0)

        # Cutters
        for w in self.cutting_workers or []:
            if not w.worker:
                continue
            emp = frappe.get_doc("Employee", w.worker)
            rate = (emp.ctc or 0) / 22 / 8
            total_cw += rate * (w.total_hours or 0)

        # Separators
        for w in self.separating_workers or []:
            if not w.worker:
                continue
            emp = frappe.get_doc("Employee", w.worker)
            rate = (emp.ctc or 0) / 22 / 8
            total_sew += rate * (w.total_hours or 0)

        # Rolls cost
        for u in self.used_rolls or []:
            if u.roll:
                rolls = frappe.get_doc("Rolls", u.roll)
                total_rolls += (u.used_qty or 0) * (rolls.price_per_kg or 0)

        self.used_rolls_cost = total_rolls
        self.total_cost = (total_ws + total_sw + total_dw +
                           total_cw + total_sew + total_rolls +
                           (self.individual_cost or 0))

        # Update roll warehouses
        for u in self.used_rolls or []:
            if u.roll:
                u.roll_warehouse = frappe.db.get_value(
                    "Rolls", u.roll, "warehouse")

        # Clear existing parts
        self.set('cutting_parts', [])

        # Build map of BOM variants
        bom_variant_map = {}
        for pb in self.parent_boms or []:
            if not pb.parent_bom:
                continue
            bom_doc = frappe.get_doc('BOM', pb.parent_bom)
            variants = []
            for item in bom_doc.items or []:
                vs = frappe.get_all('Item',
                    filters={'variant_of': item.item_code, 'disabled': 0},
                    fields=['name'])
                variants += [v.name for v in vs]
            bom_variant_map[pb.parent_bom] = variants

        # Generate parts for each roll
        for u in self.used_rolls or []:
            lap = u.lap or 0
            color = (u.color or '').strip()
            if lap <= 0 or not color:
                continue

            for sm in self.size_matrix or []:
                raw = (sm.size or '').strip()
                size_val = self.SIZE_MAP.get(raw, raw)
                qty_per = sm.qty or 0
                total_qty = lap * qty_per
                if total_qty <= 0:
                    continue

                bom_link = sm.bom_link
                if not bom_link or bom_link not in bom_variant_map:
                    continue

                for variant_code in bom_variant_map[bom_link]:
                    attrs = frappe.get_all(
                        'Item Variant Attribute',
                        filters={'parent': variant_code},
                        fields=['attribute', 'attribute_value']
                    )
                    attr_map = {
                        a.attribute.strip().lower(): (a.attribute_value or '').strip()
                        for a in attrs
                    }
                    color_val = (attr_map.get('color') or
                                 attr_map.get('colour'))
                    size_attr = attr_map.get('size')

                    if color_val == color and size_attr == str(size_val):
                        cp = self.append('cutting_parts', {})
                        cp.part = variant_code
                        cp.quantity = total_qty
                        cp.warehouse = self.distination_warehouse
                        cp.roll_relation = u.roll
                        cp.parent_bom = bom_link

        # Distribute each roll’s cost across its parts
        for u in self.used_rolls or []:
            if not u.roll:
                continue
            used_qty = u.used_qty or 0
            rate = frappe.get_doc("Rolls", u.roll).price_per_kg or 0
            total_roll_cost = used_qty * rate

            parts_for_roll = [cp for cp in (self.cutting_parts or [])
                              if cp.roll_relation == u.roll]
            total_parts_qty = sum(cp.quantity for cp in parts_for_roll) or 1
            for cp in parts_for_roll:
                cp.part_cost = total_roll_cost / total_parts_qty

        




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
            if not u.roll:
                continue
            r = frappe.get_doc("Rolls", u.roll)
            used = u.used_qty or 0
            r.weight = (r.weight or 0) - used
            ute = r.append("used_time", {})
            ute.operation = self.name
            ute.weight_used = used
            r.save()

        # 2) Create custom Parts Batch per operation, BOM, and roll
        parts_batches = {}

        # First pass: insert and collect parts
        for cp in self.cutting_parts:
            if not cp.part or (cp.quantity or 0) <= 0:
                continue

            bom = cp.parent_bom
            roll = cp.roll_relation
            key = (self.name, bom, roll)

            if key not in parts_batches:
                batch_name = f"{bom}-{roll}-{self.name}"
                batch = frappe.get_doc({
                    "doctype": "Parts Batch",
                    "batch_name": batch_name
                })
                batch.insert()
                parts_batches[key] = batch

            # append each part before any submission
            parts_batches[key].append("parts", {
                "part": cp.part,
                "qty": cp.quantity
            })

        # Save all batches (so that the child additions are persisted)
        for batch in parts_batches.values():
            batch.save()

        # Second pass: submit them now that all child rows are in place
        for batch in parts_batches.values():
            batch.submit()
    

        # 3) Material Receipt for all cut parts
        receipt = frappe.new_doc("Stock Entry")
        receipt.purpose = receipt.stock_entry_type = "Material Receipt"
        receipt.company = company

        for cp in self.cutting_parts:
            if not cp.part or (cp.quantity or 0) <= 0:
                continue
            receipt.append("items", {
                "item_code": cp.part,
                "qty": cp.quantity,
                "uom": frappe.db.get_value("Item", cp.part, "stock_uom"),
                "t_warehouse": cp.warehouse,
                "allow_zero_valuation_rate": 1
            })

        if receipt.items:
            receipt.insert()
            receipt.submit()
            self.db_set("receipt_entry_name", receipt.name)


        # 4) Submit parts batch
        
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
            if not u.roll:
                continue
            r = frappe.get_doc("Rolls", u.roll)
            used = u.used_qty or 0
            r.weight = (r.weight or 0) + used
            for ut in list(r.used_time or []):
                if ut.operation == self.name:
                    r.remove(ut)
            r.save()

        # 3) Delete created Parts Batches for this operation
        batches = frappe.get_all(
            "Parts Batch",
            filters={"batch_name": ["like", f"%-{self.name}"]},
            fields=["name"]
        )
        for b in batches:
            try:
                pb = frappe.get_doc("Parts Batch", b.name)
                pb.cancel()
            except Exception:
                frappe.log_error(f"Failed to cancel Parts Batch {b.name}")

