# Copyright (c) 2025, samidev016 and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
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
        se.from_bom             = 0  # we are manually adding all items
        se.company              = self.company
        se.set_posting_time     = 1

        # Add Finished Good row
        se.append("items", {
            "item_code": self.production_item,
            "qty": self.produced_quantity,
            "t_warehouse": self.warehouse,
            "is_finished_item": 1,
            "allow_zero_valuation_rate": 1
        })

        # Add Raw Material rows from your child table
        for row in self.raw_materials:
            se.append("items", {
                "item_code": row.material,
                "qty": row.required_quantity,
                "s_warehouse": row.item_warehouse,
                "batch_no": row.batch_no,
                "allow_zero_valuation_rate": 1
            })

        # Save and submit
        se.insert(ignore_permissions=True)
        se.submit()

        self.db_set("stock_entry", se.name)
