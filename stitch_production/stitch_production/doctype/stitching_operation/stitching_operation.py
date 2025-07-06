import frappe
from frappe.model.document import Document
import re

def clean_barcode(value):
    if not value:
        return ""
    value = re.sub(r"<[^>]*>", "", value)
    return value.replace("\n", "").replace("\r", "").replace("\u00a0", "").strip().lower()

class StitchingOperation(Document):
    def before_save(self):
        self.finish_goods = []

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

    def on_submit(self):
        if not self.finish_goods or not self.distination_warehouse:
            frappe.throw(_("No Finish Goods found or no distination warehouse"))
            return

        company = frappe.defaults.get_user_default("Company")

        stock_entry = frappe.new_doc("Stock Entry")
        stock_entry.purpose = stock_entry.stock_entry_type = "Material Receipt"
        stock_entry.company = company
        #allow valuation rate to be set
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
            frappe.msgprint(f"Adding item {fg.item} with rate {fg.cost_per_one_adding_assemblying}")
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

    def on_cancel(self):
        if self.stock_entry_name:
            try:
                stock_entry = frappe.get_doc("Stock Entry", self.stock_entry_name)
                if stock_entry.docstatus == 1:
                    stock_entry.cancel()

                for fg in self.finish_goods:
                    fg.db_set("stock_entry_name", None)

                    # ✅ Revert is_stitched = 0 in child row inside Assemblying
                    asm_doc = frappe.get_doc("Assemblying", fg.operation)
                    for row in asm_doc.finish_goods:
                        if clean_barcode(row.barcode) == clean_barcode(fg.barcode):
                            row.is_stitched = 0
                    asm_doc.save()

            except Exception as e:
                frappe.throw(f"Unable to cancel Stock Entry {self.stock_entry_name}: {e}")


