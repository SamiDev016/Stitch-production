import frappe
from frappe.model.document import Document
import re
import math
import unicodedata

def clean_barcode(value):
    if not value:
        return ""

    value = re.sub(r"<[^>]*>", "", value)
    value = unicodedata.normalize('NFKD', value).encode('ascii', 'ignore').decode('ascii')
    value = value.replace("\u00a0", " ")
    value = value.replace("\n", " ").replace("\r", " ")
    value = re.sub(r"\s+", " ", value)

    return value.strip().lower()

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
                frappe.msgprint(f"Finish good {fg.barcode or fg.item} has no operation linked." , raise_exception=1)
                continue

            ass_doc = frappe.get_doc("Assemblying", fg.operation)
            matched_fg = next((fgg for fgg in ass_doc.finish_goods if clean_barcode(fgg.barcode) == clean_barcode(fg.barcode)), None)

            if not matched_fg:
                frappe.msgprint(f"No matching finish good in Assemblying for barcode {fg.barcode}", raise_exception=1)
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
                
        

        

    def before_submit(self):
        if not self.used_parts_batches:
            frappe.throw(_("No Used Parts Batches found"))
            return

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

        def issue_part(part_code, qty, warehouse, rate,batch_number):
            uom = frappe.db.get_value("Item", part_code, "stock_uom")
            issue_entry.append("items", {
                "item_code": part_code,
                "qty": qty,
                "uom": uom,
                "stock_uom": uom,
                "conversion_factor": 1,
                "s_warehouse": warehouse,
                "allow_zero_valuation_rate": 1,
                "use_serial_batch_fields": 1,
                "batch_no": batch_number
            })

        for fg in self.finish_goods:
            operation_name = fg.operation
            fg_qty = fg.qty

            if not operation_name:
                frappe.throw(f"Missing operation for Finish Good: {fg.item}")

            for used_batch in self.used_parts_batches:
                if not used_batch.batch:
                    continue

                pb_doc = frappe.get_doc("Parts Batch", used_batch.batch)
                if not pb_doc.parts:
                    continue

                warehouse = used_batch.warehouse

                for reserve in pb_doc.batches_reserves:
                    if reserve.operation != operation_name:
                        continue

                    part_code = reserve.part
                    reserved_qty = reserve.reserved_qty or 0

                    if not part_code or reserved_qty <= 0:
                        continue

                    part_row = next((p for p in pb_doc.parts if p.part == part_code), None)
                    if not part_row:
                        frappe.throw(f"Part {part_code} not found in parts table for batch {pb_doc.name}")

                    if not part_row.cost_per_one:
                        frappe.throw(f"Missing cost per one for part {part_code} in batch {pb_doc.name}")

                    issue_part(part_code, reserved_qty, warehouse, part_row.cost_per_one,part_row.batch_number)

                    reserve.reserved_qty = 0

                pb_doc.save()
        if issue_entry.items:
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

                    if fg.operation:
                        asm_doc = frappe.get_doc("Assemblying", fg.operation)
                        for row in asm_doc.finish_goods:
                            if clean_barcode(row.barcode) == clean_barcode(fg.barcode):
                                row.is_stitched = 0
                        asm_doc.save()

            except Exception as e:
                frappe.throw(f"Failed to cancel Stock Entry {self.stock_entry_name}: {e}")

        if self.issue_entry_name:
            try:
                issue_entry = frappe.get_doc("Stock Entry", self.issue_entry_name)
                if issue_entry.docstatus == 1:
                    issue_entry.cancel()
            except Exception as e:
                frappe.throw(f"Failed to cancel Issue Entry {self.issue_entry_name}: {e}")

        for fg in self.finish_goods:
            if not fg.operation:
                continue

            for used in self.used_parts_batches:
                if not used.batch:
                    continue

                pb_doc = frappe.get_doc("Parts Batch", used.batch)

                for part_row in pb_doc.parts:
                    if not part_row.part or not part_row.qty_of_finished_goods:
                        continue
                        
                    restore_amount = used.qty * part_row.qty_of_finished_goods

                    for reserve in pb_doc.batches_reserves:
                        if reserve.part == part_row.part and reserve.operation == fg.operation:
                            reserve.reserved_qty += restore_amount

                pb_doc.save()

        self.db_set("stock_entry_name", None)
        self.db_set("issue_entry_name", None)
