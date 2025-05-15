# Copyright (c) 2025, samidev016 and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import nowdate, nowtime
from frappe import _

class ProductionOperation(Document):

    def validate(self):
        if not self.poduction_bom:
            frappe.throw(_("Please select a Production BOM"))
        if not self.produced_quantity:
            frappe.throw(_("Please enter a quantity to produce"))

        # Get item from BOM
        bom = frappe.get_doc("BOM", self.poduction_bom)
        self.production_item = bom.item

    def on_submit(self):
        se = frappe.new_doc("Stock Entry")
        se.stock_entry_type     = "Manufacture"
        se.bom_no               = self.poduction_bom
        se.production_item      = self.production_item
        se.fg_warehouse         = self.warehouse
        se.produced_qty         = self.produced_quantity
        se.from_bom             = 0
        se.company              = self.company
        se.set_posting_time     = 1
        se.posting_date         = nowdate()
        se.posting_time         = nowtime()

        # Add Finished Good
        se.append("items", {
            "item_code": self.production_item,
            "qty": self.produced_quantity,
            "t_warehouse": self.warehouse,
            "is_finished_item": 1,
            "allow_zero_valuation_rate": 1,
            "use_serial_batch_fields": 0  # Avoid SABB creation
        })

        # Add Raw Materials
        for row in self.raw_materials:
            item_row = {
                "item_code": row.material,
                "qty": row.required_quantity,
                "s_warehouse": row.item_warehouse,
                "allow_zero_valuation_rate": 1,
                "use_serial_batch_fields": 1  # Force SABB usage
            }

            # Optional: only set batch_no if not already used
            if row.batch_no:
                existing_bundle = frappe.db.exists("Serial and Batch Bundle", {
                    "production_operation": self.name,
                    "item": row.material
                })
                if not existing_bundle:
                    item_row["batch_no"] = row.batch_no

            se.append("items", item_row)

        # Save and submit
        se.insert(ignore_permissions=True)
        se.submit()

        # Link back
        self.db_set("stock_entry", se.name)
        frappe.msgprint(_("Stock Entry {0} has been created and submitted.").format(se.name))
