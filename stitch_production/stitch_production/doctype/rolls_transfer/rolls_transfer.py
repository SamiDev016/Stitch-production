# your_app/your_module/doctype/rolls_transfer/rolls_transfer.py

import frappe
from frappe.model.document import Document
from frappe import _

class RollsTransfer(Document):

    def validate(self):
        # Each row has its own source warehouse in r.warehouse
        for r in self.get("rolls") or []:
            if r.roll and r.warehouse:
                roll_doc = frappe.get_doc("Rolls", r.roll)
                if roll_doc.warehouse != r.warehouse:
                    frappe.throw(
                        _(f"Roll {r.roll} is not in warehouse {r.warehouse}"),
                        title=_("Invalid Source Warehouse")
                    )

    def on_submit(self):
        rows = self.get("rolls") or []
        if not rows:
            frappe.throw(_("Please add at least one roll to transfer."))

        # Use the first row's warehouse as the Stock Entry's from_warehouse
        first_src = rows[0].warehouse
        se = frappe.new_doc("Stock Entry")
        se.stock_entry_type = "Material Transfer"
        se.from_warehouse   = first_src
        se.to_warehouse     = self.destination_warehouse

        for r in rows:
            if not r.roll:
                continue

            # Update the Rolls record itself
            roll_doc = frappe.get_doc("Rolls", r.roll)
            roll_doc.warehouse = self.destination_warehouse
            roll_doc.save(ignore_permissions=True)

            # Append a line for this roll
            se.append("items", {
                "item_code":   roll_doc.fabric_item,
                "qty":         roll_doc.weight,
                "uom":         "Kg",
                "stock_uom":   "Kg",
                "s_warehouse": r.warehouse,
                "t_warehouse": self.destination_warehouse
            })

        se.insert(ignore_permissions=True)
        se.submit()

    def on_cancel(self):
        frappe.throw(_("Rolls Transfer cannot be cancelled once submitted."))
