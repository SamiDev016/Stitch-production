import frappe
from frappe.model.document import Document
import re
import math

def clean_barcode(value):
    if not value:
        return ""
    value = re.sub(r"<[^>]*>", "", value)
    return value.replace("\n", "").replace("\r", "").replace("\u00a0", "").strip().lower()

class StitchingOperation(Document):
    def before_save(self):
        self.set("finish_goods", [])

        for row in self.assembled_parts:
            if not row.barcode:
                continue

            search_barcode = clean_barcode(row.barcode)

            for asm in frappe.get_all("Assemblying", fields=["name"]):
                asm_doc = frappe.get_doc("Assemblying", asm["name"])
                for fg in asm_doc.finish_goods:
                    if not fg.barcode:
                        continue

                    fg_barcode = clean_barcode(fg.barcode)

                    if fg_barcode == search_barcode and fg.qty > 0 and fg.is_stitched == 0:
                        self.append("finish_goods", {
                            "item": fg.item,
                            "qty": fg.qty,
                            "barcode": fg.barcode,
                            "operation": asm_doc.name,
                            "cost_per_one_adding_assemblying": fg.cost_per_one_adding_assemblying,
                            "total_finish_good_adding_assemblying": fg.total_finish_good_adding_assemblying,
                            "cost": fg.cost,
                            "cost_per_one": fg.cost_per_one
                        })
                        break

        for ws in self.stitching_workers:
            if not ws.worker:
                continue
            emp = frappe.get_doc("Employee", ws.worker)
            rate = (emp.ctc or 0) / 22 / 8
            ws.hourly_rate = rate
            ws.employee_cost = rate * (ws.total_hours or 0)
        
        self.total_workers_cost = sum(ws.employee_cost for ws in self.stitching_workers)
        self.total_cost = self.total_workers_cost + (self.extra_cost or 0) + sum(fg.total_finish_good_adding_assemblying for fg in self.finish_goods)
        added_cost = 0.0

        if not self.finish_goods:
            frappe.msgprint("No Finish Goods found", raise_exception=1)
            return
        
        fg_qty = sum(fg.qty for fg in self.finish_goods)
        added_cost = (self.extra_cost + self.total_workers_cost) / fg_qty
        
        for fg in self.finish_goods:
            fg.cost_per_one_adding_assemblying += added_cost
            fg.total_finish_good_adding_assemblying += fg.qty * added_cost
            fg.cost += fg.qty * added_cost
            fg.cost_per_one += added_cost
        
        fg_map = {}

        for fg in self.finish_goods:
            if not fg.operation:
                frappe.msgprint(f"Finish good {fg.barcode or fg.item} has no operation linked.")
                continue

            ass_doc = frappe.get_doc("Assemblying", fg.operation)
            matched_fg = next((fgg for fgg in ass_doc.finish_goods if clean_barcode(fgg.barcode) == clean_barcode(fg.barcode)), None)

            if not matched_fg:
                frappe.msgprint(f"No matching finish good in Assemblying for barcode {fg.barcode}")
                continue

            finish_index = matched_fg.finish_good_index

            fg_map[fg.barcode] = []

            for mb in ass_doc.main_batches:
                if mb.finish_good_index == finish_index:
                    warehouse = ass_doc.distination_warehouse
                    fg_map[fg.barcode].append({
                        "batch": mb.batch,
                        "qty": mb.parts_qty,
                        "source": "main",
                        "warehouse": warehouse
                    })

            for ob in ass_doc.other_batches:
                if ob.finish_good_index == finish_index:
                    warehouse = ass_doc.distination_warehouse
                    fg_map[fg.barcode].append({
                        "batch": ob.batch,
                        "qty": ob.qty,
                        "source": "other",
                        "warehouse": warehouse
                    })

        self.set("used_parts_batches", [])
        for barcode, batches in fg_map.items():
            for entry in batches:
                self.append("used_parts_batches", {
                    "batch": entry["batch"],
                    "qty": entry["qty"],
                    "warehouse": entry["warehouse"]
                })

        

            
    def on_submit(self):
        if not self.finish_goods or not self.distination_warehouse:
            frappe.throw(_("No Finish Goods found or no distination warehouse"))
            return

        company = frappe.defaults.get_user_default("Company")

        stock_entry = frappe.new_doc("Stock Entry")
        stock_entry.purpose = stock_entry.stock_entry_type = "Material Receipt"
        stock_entry.company = company
        stock_entry.allow_valuation_rate = 1

        def add_item(item_code, qty, warehouse, rate):
            uom = frappe.db.get_value("Item", item_code, "stock_uom")
            stock_entry.append("items", {
                "item_code": item_code,
                "qty": qty,
                "basic_rate": rate,
                "uom": uom,
                "stock_uom": uom,
                "conversion_factor": 1,
                "t_warehouse": warehouse,
                "allow_zero_valuation_rate": 1,
                "valuation_rate": rate,
                "set_basic_rate_manually": 1

            })

        for fg in self.finish_goods:
            add_item(fg.item, fg.qty, self.distination_warehouse, fg.cost_per_one_adding_assemblying)

        if stock_entry.items:
            stock_entry.insert()
            stock_entry.submit()

        self.db_set("stock_entry_name", stock_entry.name)
        for fg in self.finish_goods:
            fg.db_set("stock_entry_name", stock_entry.name)

            asm_doc = frappe.get_doc("Assemblying", fg.operation)
            for row in asm_doc.finish_goods:
                if clean_barcode(row.barcode) == clean_barcode(fg.barcode):
                    row.is_stitched = 1
            asm_doc.save()

        
        issue_entry = frappe.new_doc("Stock Entry")
        issue_entry.purpose = issue_entry.stock_entry_type = "Material Issue"
        issue_entry.company = company
        issue_entry.allow_valuation_rate = 1

        def issue_part(part_code, qty, warehouse, rate):
            uom = frappe.db.get_value("Item", part_code, "stock_uom")
            issue_entry.append("items", {
                "item_code": part_code,
                "qty": qty,
                "uom": uom,
                "stock_uom": uom,
                "conversion_factor": 1,
                "s_warehouse": warehouse,
                "allow_zero_valuation_rate": 1,
                "valuation_rate": rate,
                "set_basic_rate_manually": 1,
                "basic_rate": rate,
            })

        # Issue parts for each used batch
        for batch in self.used_parts_batches:
            if not batch.batch:
                continue

            pb_doc = frappe.get_doc("Parts Batch", batch.batch)
            if not pb_doc.parts:
                continue

            batch_qty = batch.qty

            reserved_qtys = [int(p.reserved_qty) for p in pb_doc.parts if p.reserved_qty and float(p.reserved_qty).is_integer()]
            pgcd = math.gcd(*reserved_qtys) if reserved_qtys else 1

            if pgcd <= 0:
                frappe.msgprint(f"Invalid PGCD for batch {batch.batch}")
                continue

            for part in pb_doc.parts:
                if not part.part or not part.reserved_qty or not part.cost_per_one:
                    continue

                per_unit_reserved = part.reserved_qty / pgcd
                used_qty = per_unit_reserved * batch_qty

                if used_qty <= 0:
                    continue

                if (part.reserved_qty or 0) < used_qty:
                    frappe.throw(f"Not enough reserved qty for part {part.part} in batch {batch.batch}. Needed: {used_qty}, Reserved: {part.reserved_qty}")


                warehouse = batch.warehouse

                frappe.msgprint(f"Issuing {used_qty} of {part.part} from {warehouse}")
                frappe.msgprint(f"cost per one: {part.cost_per_one}")

                issue_part(part.part, used_qty, warehouse, part.cost_per_one)

                for p in pb_doc.parts:
                    if p.part == part.part:
                        p.reserved_qty -= used_qty
                        if p.reserved_qty < 0:
                            p.reserved_qty = 0
                        if p.qty:
                            p.qty -= used_qty
                            if p.qty < 0:
                                p.qty = 0

                pb_doc.save()

        issue_entry.insert()
        issue_entry.submit()

        self.db_set("issue_entry_name", issue_entry.name)
        



    def on_cancel(self):
        if self.stock_entry_name:
            try:
                stock_entry = frappe.get_doc("Stock Entry", self.stock_entry_name)
                if stock_entry.docstatus == 1:
                    stock_entry.cancel()

                for fg in self.finish_goods:
                    fg.db_set("stock_entry_name", None)

                    asm_doc = frappe.get_doc("Assemblying", fg.operation)
                    for row in asm_doc.finish_goods:
                        if clean_barcode(row.barcode) == clean_barcode(fg.barcode):
                            row.is_stitched = 0
                    asm_doc.save()

            except Exception as e:
                frappe.throw(f"Unable to cancel Stock Entry {self.stock_entry_name}: {e}")

