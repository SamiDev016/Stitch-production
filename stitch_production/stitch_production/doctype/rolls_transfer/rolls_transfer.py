# your_app/your_module/doctype/rolls_transfer/rolls_transfer.py

import frappe
from frappe.model.document import Document
from frappe import _
from datetime import datetime

class RollsTransfer(Document):

    def validate(self):
        # Ensure every row’s source matches the Roll’s current warehouse
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

        # Parse movement_date into date + time
        if isinstance(self.movement_date, str):
            # e.g. "2025-05-19T14:35:00" or "2025-05-19 14:35:00"
            dt = datetime.fromisoformat(self.movement_date)
        else:
            dt = self.movement_date

        # Build Stock Entry
        first_src = rows[0].warehouse
        se = frappe.new_doc("Stock Entry")
        se.stock_entry_type = "Material Transfer"
        se.from_warehouse   = first_src
        se.to_warehouse     = self.destination_warehouse
        se.set_posting_time = 1
        se.posting_date     = dt.date().isoformat()
        se.posting_time     = dt.time().strftime("%H:%M:%S")
        # Tag so we can find it on cancel
        se.remarks          = self.name

        # Add each roll as an “item” line
        for r in rows:
            if not r.roll:
                continue

            roll_doc = frappe.get_doc("Rolls", r.roll)

            # Immediately update the Roll’s warehouse
            roll_doc.warehouse = self.destination_warehouse
            roll_doc.save(ignore_permissions=True)

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
        # 1) Find & cancel the Stock Entry we created
        entries = frappe.db.get_all(
            "Stock Entry",
            filters={
                "purpose": "Material Transfer",
                "remarks": self.name,
                "docstatus": 1
            },
            fields=["name"]
        )
        for row in entries:
            try:
                se = frappe.get_doc("Stock Entry", row.name)
                se.cancel()
            except frappe.ValidationError:
                # already cancelled or locked
                pass

        # 2) Move each Roll back to its original warehouse
        for r in (self.get("rolls") or []):
            if not r.roll or not r.warehouse:
                continue

            roll_doc = frappe.get_doc("Rolls", r.roll)
            # r.warehouse is the source we validated earlier
            roll_doc.warehouse = r.warehouse
            roll_doc.save(ignore_permissions=True)
