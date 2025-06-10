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
        # Calculate total cost components
        total_ws = total_rolls = 0.0
        total_sw = 0.0
        total_dw = 0.0
        total_cw = 0.0
        total_sew = 0.0



        if self.workstation:
            ws = frappe.get_doc("Workstation", self.workstation)
            total_ws = ws.hour_rate * (self.total_hours or 0)

        for w in self.spreading_workers or []:
            if not w.worker:
                continue
            emp = frappe.get_doc("Employee", w.worker)
            rate = (emp.ctc or 0) / 22 / 8
            total_sw += rate * (w.total_hours or 0)

        for w in self.drawing_workers or []:
            if not w.worker:
                continue
            emp = frappe.get_doc("Employee", w.worker)
            rate = (emp.ctc or 0) / 22 / 8
            total_dw += rate * (w.total_hours or 0)

        for w in self.cutting_workers or []:
            if not w.worker:
                continue
            emp = frappe.get_doc("Employee", w.worker)
            rate = (emp.ctc or 0) / 22 / 8
            total_cw += rate * (w.total_hours or 0)

        for w in self.separating_workers or []:
            if not w.worker:
                continue
            emp = frappe.get_doc("Employee", w.worker)
            rate = (emp.ctc or 0) / 22 / 8
            total_sew += rate * (w.total_hours or 0)


        for u in self.used_rolls or []:
            if u.roll:
                rolls = frappe.get_doc("Rolls", u.roll)
                total_rolls += (u.used_qty or 0) * (rolls.price_per_kg or 0)

        self.used_rolls_cost = total_rolls
        self.total_cost = total_ws + total_sw + total_dw + total_cw + total_sew + total_rolls + self.individual_cost

    # Propagate roll warehouse
        for u in self.used_rolls or []:
            if u.roll:
                u.roll_warehouse = frappe.db.get_value("Rolls", u.roll, "warehouse")

    # Build cutting_parts
        self.set('cutting_parts', [])

    # Prepare map: {bom_name: [variant_names]}
        bom_variant_map = {}
        for pb in self.parent_boms or []:
            if not pb.parent_bom:
                continue
            variant_list = []
            for item in frappe.get_doc('BOM', pb.parent_bom).items or []:
                vs = frappe.get_all('Item',
                    filters={'variant_of': item.item_code, 'disabled': 0},
                    fields=['name'])
                variant_list += [v.name for v in vs]
            bom_variant_map[pb.parent_bom] = variant_list

        parts = []
        for u in self.used_rolls or []:
            lap = u.lap or 0
            color = (u.color or '').strip()
            if lap <= 0 or not color:
                continue

        for sm in self.size_matrix or []:
            raw = (sm.size or '').strip()
            size_val = self.SIZE_MAP.get(raw, raw)
            qty_per = sm.qty or 0
            qty = lap * qty_per
            if qty <= 0:
                continue

            bom_link = sm.bom_link
            if not bom_link or bom_link not in bom_variant_map:
                continue

            for v in bom_variant_map[bom_link]:
                attrs = frappe.get_all(
                    'Item Variant Attribute',
                    filters={'parent': v},
                    fields=['attribute', 'attribute_value']
                )

                amap = {
                    a.attribute.strip().lower(): (a.attribute_value or '').strip()
                    for a in attrs
                }

                # Handle both 'color' and 'colour'
                color_value = (
                    amap.get('color') or
                    amap.get('colour')
                )

                if color_value == color and amap.get('size') == str(size_val):
                    parts.append({
                        'variant': v,
                        'quantity': qty,
                        'roll_relation': u.roll,
                        'parent_bom': bom_link
                    })

        for p in parts:
            cp = self.append('cutting_parts', {})
            cp.part           = p['variant']
            cp.quantity       = p['quantity']
            cp.warehouse      = self.distination_warehouse
            cp.roll_relation  = p['roll_relation']
            cp.parent_bom     = p['parent_bom']

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
        frappe.msgprint(f"Processing {len(self.cutting_parts)} cutting parts")

        for cp in self.cutting_parts:
            if not cp.part or (cp.quantity or 0) <= 0:
                frappe.msgprint(f"Skipping part - Missing Item or Quantity: {cp.part or 'No Item'}, Qty: {cp.quantity}")
                continue

            # ensure each cutting part has parent_bom set
            bom = cp.parent_bom
            roll = cp.roll_relation
            if not bom or not roll:
                frappe.msgprint(f"BOM/Roll missing for Part: {cp.part} | BOM: {bom}, Roll: {roll}")
                continue

            # grouping key: (operation, BOM, roll)
            key = (self.name, bom, roll)

            if key not in parts_batches:
                batch_name = f"{bom}-{roll}-{self.name}"
                # create Parts Batch if not exists
                
                aa = frappe.get_doc({
                    "doctype": "Parts Batch",
                    "batch_name": batch_name
                })  
                aa.insert()
                frappe.msgprint(f"Created new Parts Batch: {batch_name}")
                
                parts_batches[key] = aa

            frappe.msgprint(f"Parts batch: {parts_batches[key].name}")
            # append to the custom Parts Batch child table
            pb = parts_batches[key]
            frappe.msgprint(f"Adding Part {cp.part} (Qty: {cp.quantity}) to Batch {pb.name}")
            pb.append("parts", {
                "part": cp.part,
                "qty": cp.quantity
            })
            pb.save()

        # 3) Material Receipt (one entry) for all cut parts
        receipt = frappe.new_doc("Stock Entry")
        receipt.purpose = receipt.stock_entry_type = "Material Receipt"
        receipt.company = company
        items_count = 0  # Counter for debug

        for cp in self.cutting_parts:
            if not cp.part or (cp.quantity or 0) <= 0:
                continue
                
            items_count += 1  # Increment counter
            receipt.append("items", {
                "item_code": cp.part,
                "qty": cp.quantity,
                "uom": frappe.db.get_value("Item", cp.part, "stock_uom"),
                "t_warehouse": cp.warehouse,
                "allow_zero_valuation_rate": 1
            })

        if receipt.items:
            frappe.msgprint(f"Creating Material Receipt with {items_count} items")
            receipt.insert()
            receipt.submit()
            frappe.msgprint(f"Material Receipt created: {receipt.name}")
            self.db_set("receipt_entry_name", receipt.name)
        else:
            frappe.msgprint("No valid items found for Material Receipt")

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
