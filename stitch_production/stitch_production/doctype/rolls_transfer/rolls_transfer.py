# Copyright (c) 2025, samidev016 and contributors
# For license information, please see license.txt

# import frappe
import frappe
from frappe.model.document import Document
from frappe import _

class RollsTransfer(Document):
    def validate(self):
        # Ensure the selected Roll is currently in the source warehouse
        if self.roll and self.source_warehouse:
            roll = frappe.get_doc("Rolls", self.roll)
            if roll.warehouse != self.source_warehouse:
                frappe.throw(
                    _(f"Roll {self.roll} is not in warehouse {self.source_warehouse}"),
                    title=_("Invalid Source Warehouse")
                )

    def on_submit(self):
        # 1) Load and update the Rolls record's warehouse
        roll = frappe.get_doc("Rolls", self.roll)
        roll.warehouse = self.destination_warehouse
        roll.save(ignore_permissions=True)

        # 2) Create a Stock Entry (Material Transfer) to move the fabric stock
        se = frappe.new_doc("Stock Entry")
        se.stock_entry_type = "Material Transfer"
        se.from_warehouse   = self.source_warehouse
        se.to_warehouse     = self.destination_warehouse
        se.append("items", {
            "item_code":   roll.fabric_item,
            "qty":         roll.weight,
            "uom":         "Kg",
            "stock_uom":   "Kg",
            "s_warehouse": self.source_warehouse,
            "t_warehouse": self.destination_warehouse
        })
        se.insert(ignore_permissions=True)
        se.submit()

    def on_cancel(self):
        # Optional: reverse the transfer if needed
        frappe.throw(_("Rolls Transfer cannot be cancelled once submitted."))

