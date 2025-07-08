import frappe
from frappe.model.document import Document
from frappe.utils import generate_hash

class cuttingoperation(Document):

    def before_save(self):
        total_ws = 0.0
        total_rolls = 0.0
        workstation_net_rate = 0.0
        total_spreading_workers_cost = 0.0
        total_drawing_workers_cost = 0.0
        total_cutting_workers_cost = 0.0
        

        total_cost_bom = 0
        for b in self.parent_boms or []:
            total_cost_bom += (b.cost_bom or 0)

        if total_cost_bom != 100:
            frappe.throw("Total cost of BOMs should be 100%")

        if self.workstation:
            ws = frappe.get_doc("Workstation", self.workstation)
            total_ws = ws.hour_rate * (self.total_hours or 0)
            workstation_net_rate = ws.hour_rate
        self.workstation_net_rate = workstation_net_rate
        self.workstation_total_cost = total_ws

        for spreading_w in self.spreading_workers:
            emp = frappe.get_doc("Employee", spreading_w.worker)
            rate = (emp.ctc or 0) / 22 / 8
            spreading_w.hourly_rate = rate
            spreading_w.employee_cost = rate * (spreading_w.total_hours or 0)
            total_spreading_workers_cost += rate * (spreading_w.total_hours or 0)
        
        self.total_spreading_workers_cost = total_spreading_workers_cost

        for drawing_w in self.drawing_workers:
            emp = frappe.get_doc("Employee", drawing_w.worker)
            rate = (emp.ctc or 0) / 22 / 8
            drawing_w.hourly_rate = rate
            drawing_w.employee_cost = rate * (drawing_w.total_hours or 0)
            total_drawing_workers_cost += rate * (drawing_w.total_hours or 0)
        self.total_drawing_workers_cost = total_drawing_workers_cost

        for cutting_w in self.cutting_workers:
            emp = frappe.get_doc("Employee", cutting_w.worker)
            rate = (emp.ctc or 0) / 22 / 8
            cutting_w.hourly_rate = rate
            cutting_w.employee_cost = rate * (cutting_w.total_hours or 0)
            total_cutting_workers_cost += rate * (cutting_w.total_hours or 0)
        self.total_cutting_workers_cost = total_cutting_workers_cost

        for u in self.used_rolls or []:
            if u.roll:
                rolls = frappe.get_doc("Rolls", u.roll)
                total_rolls += (u.used_qty or 0) * (rolls.price_per_kg or 0)

        self.used_rolls_cost = total_rolls
        self.total_cost = (
            total_ws + total_spreading_workers_cost + total_drawing_workers_cost + total_cutting_workers_cost + total_rolls + (self.individual_cost or 0)
        )
        self.operation_cost = self.total_cost - self.used_rolls_cost




        

        for u in self.used_rolls or []:
            if u.roll:
                u.roll_warehouse = frappe.db.get_value("Rolls", u.roll, "warehouse")

        self.set('cutting_parts', [])

        bom_variant_map = {}
        for pb in self.parent_boms or []:
            if not pb.parent_bom:
                continue
            bom_doc = frappe.get_doc('BOM', pb.parent_bom)
            variant_qty_map = []
            for item in bom_doc.items or []:
                vs = frappe.get_all('Item',
                    filters={'variant_of': item.item_code, 'disabled': 0},
                    fields=['name'])
                for v in vs:
                    variant_qty_map.append({
                        "variant": v.name,
                        "qty": item.qty or 1
                    })
            bom_variant_map[pb.parent_bom] = variant_qty_map

        for u in self.used_rolls or []:
            lap = u.lap or 0
            color = (u.color or '').strip()
            if lap <= 0 or not color:
                continue

            for sm in self.size_matrix or []:
                index = 1
                if not sm.size:
                    continue
                #size_doc = frappe.get_doc("Item Attribute Value", sm.size)
                size_doc = frappe.get_doc("Size", sm.size)
                size_val = size_doc.size

                qty_per = sm.qty or 0
                total_qty = lap * qty_per
                if total_qty <= 0:
                    continue

                bom_link = sm.bom_link
                if not bom_link or bom_link not in bom_variant_map:
                    continue

                for item in bom_variant_map[bom_link]:
                    variant_code = item["variant"]
                    bom_item_qty = item["qty"]

                    attrs = frappe.get_all(
                        'Item Variant Attribute',
                        filters={'parent': variant_code},
                        fields=['attribute', 'attribute_value']
                    )
                    attr_map = {
                        a.attribute.strip().lower(): (a.attribute_value or '').strip()
                        for a in attrs
                    }
                    color_val = (attr_map.get('color') or attr_map.get('colour'))
                    size_attr = attr_map.get('size')

                    if color_val == color and size_attr == size_val:
                        cp = self.append('cutting_parts', {})
                        cp.part = variant_code
                        cp.quantity = total_qty * bom_item_qty
                        cp.warehouse = self.distination_warehouse
                        cp.roll_relation = u.roll
                        cp.parent_bom = bom_link
                        cp.size_link = sm.size
                        cp.batch_qty = total_qty

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

        parts_batches = {}
        bom_cost_map = {b.parent_bom: b.cost_bom for b in self.parent_boms if b.parent_bom}

        for cp in self.cutting_parts:
            if not cp.part or (cp.quantity or 0) <= 0:
                continue

            bom = cp.parent_bom
            roll = cp.roll_relation
            size = cp.size_link
            key = (self.name, bom, roll, size)
            bname = f"{bom}-{roll}-{size}-{self.name}"
            pgcd_qty = cp.batch_qty

            if key not in parts_batches:
                existing_name = frappe.db.get_value("Parts Batch", {"batch_name": bname}, "name")
                if existing_name:
                    batch = frappe.get_doc("Parts Batch", existing_name)
                else:
                    batch = frappe.new_doc("Parts Batch")
                    batch.batch_name = bname
                    batch.source_bom = bom
                    roll_doc = frappe.get_doc("Rolls", roll)
                    batch.color = roll_doc.color
                    batch.size = size
                    batch.pgcd_qty = pgcd_qty
                    batch.insert()

                parts_batches[key] = batch

            parts_batches[key].append("parts", {
                "part": cp.part,
                "qty": cp.quantity,
                "source_bom": bom,
            })

        bom_to_batches = {}
        for key, batch in parts_batches.items():
            bom = key[1]
            if bom not in bom_to_batches:
                bom_to_batches[bom] = []
            bom_to_batches[bom].append(batch)
        total_pgcd_qty = 0
        for bom_name, batches in bom_to_batches.items():
            total_pgcd_qty = sum(batch.pgcd_qty for batch in batches)
            bom_percent = bom_cost_map.get(bom_name, 0)
            if not (bom_percent and batches):
                continue

            bom_doc = frappe.get_doc("BOM", bom_name)
            bom_total_cost = self.total_cost * (bom_percent / 100.0)

            
            

            part_cost_map = {}
            total_part_percent = 0
            for item in bom_doc.items:
                part_code = item.item_code
                part_percent = item.custom_cost_percent or 0
                if part_percent > 0:
                    part_cost_map[part_code] = part_percent
                    total_part_percent += part_percent

            for batch in batches:
                batch.cost = 0
                batch.cost_per_unit = 0

                cost_per_batch = batch.pgcd_qty / total_pgcd_qty * bom_total_cost 

                batch.cost = cost_per_batch
                batch.cost_per_unit = cost_per_batch / batch.pgcd_qty
                for part_row in batch.parts:
                    part_code = part_row.part
                    template_code = frappe.db.get_value("Item", part_code, "variant_of")
                    part_percent = part_cost_map.get(template_code, 0)
                    qty = part_row.qty or 1
                    if part_percent > 0 and total_part_percent > 0:
                        part_total_cost = cost_per_batch * (part_percent / total_part_percent)
                        cost_per_one = part_total_cost / qty
                        part_row.cost_per_one = cost_per_one
                batch.save()

        for batch in parts_batches.values():
            barcode_value = generate_hash(batch.batch_name, 12)
            batch.db_set("serial_number_barcode", barcode_value)
            batch.source_operation = self.name
            batch.submit()

        receipt = frappe.new_doc("Stock Entry")
        receipt.purpose = receipt.stock_entry_type = "Material Receipt"
        receipt.company = company

        for cp in self.cutting_parts:
            if not cp.part or (cp.quantity or 0) <= 0:
                continue
            cost_per_one = 0
            for batch in parts_batches.values():
                for part_row in batch.parts:
                    if part_row.part == cp.part:
                        cost_per_one = part_row.cost_per_one or 0
                        break
            frappe.msgprint(f"Cost per one: {cost_per_one} for part {cp.part}")
            receipt.append("items", {
                "item_code": cp.part,
                "qty": cp.quantity,
                "uom": frappe.db.get_value("Item", cp.part, "stock_uom"),
                "t_warehouse": cp.warehouse,
                "allow_zero_valuation_rate": 1,
                "basic_rate": cost_per_one,
                "valuation_rate": cost_per_one,
                "set_basic_rate_manually": 1
            })

        if receipt.items:
            receipt.insert()
            receipt.submit()
            self.db_set("receipt_entry_name", receipt.name)
        
        self.set("batches_result", [])
        for batch in parts_batches.values():
            frappe.msgprint("Starting filling parts batch result")
            self.append("batches_result",{
                "batch":batch.name,
                "color":batch.color,
                "size":batch.size,
                "cost":batch.cost,
            })
            frappe.msgprint("Finishing filling parts batch result")

    def before_cancel(self):
        frappe.flags.ignore_linked_with = True
    def on_cancel(self):
        for field in ("stock_entry_name", "receipt_entry_name"):
            name = self.get(field)
            if name:
                try:
                    frappe.get_doc("Stock Entry", name).cancel()
                except frappe.DoesNotExistError:
                    pass

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

        batches = frappe.get_all(
            "Parts Batch",
            filters={"batch_name": ["like", f"%-{self.name}"]},
            fields=["name"]
        )
        for b in batches:
            try:
                pb = frappe.get_doc("Parts Batch", b.name)
                pb.cancel(ignore_permissions=True)
            except Exception:
                frappe.log_error(f"Failed to cancel Parts Batch {b.name}")
