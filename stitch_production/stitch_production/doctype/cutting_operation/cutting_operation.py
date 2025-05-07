import frappe
from frappe.model.document import Document
from frappe.exceptions import DoesNotExistError

class cuttingoperation(Document):

    def validate(self):
        total_ws = sum((ws.cost_per_hour or 0) * (ws.total_hours or 0)
                       for ws in self.get("workstation_cost", []))

        total_wr = sum((wr.cost_per_hour or 0) * (wr.total_hours or 0)
                       for wr in self.get("worker_cost", []))

        individual = self.individual_cost or 0
        self.total_cost = total_ws + total_wr + individual

    def on_submit(self):
        # 1) Process each used roll: deduct from Rolls.weight, log usage, and issue fabric
        for row in self.used_rolls:
            try:
                roll = frappe.get_doc("Rolls", row.roll)
            except DoesNotExistError:
                frappe.throw(f"Roll {row.roll} not found")

            used_qty = row.used_qty or 0.0
            if roll.weight < used_qty:
                frappe.throw(
                    f"Used quantity ({used_qty} Kg) exceeds available weight ({roll.weight} Kg) for Roll {roll.name}"
                )

            # a) record the usage in the Rolls.used_time child table
            roll.append('used_time', {
                'operation': self.name,
                'weight_used': used_qty
            })

            # b) decrement the roll's remaining weight
            roll.weight = roll.weight - used_qty

            # c) save both weight change and new used_time row in one go
            roll.save(ignore_permissions=True)

            # d) issue the fabric via Material Issue
            se = frappe.new_doc("Stock Entry")
            se.stock_entry_type = "Material Issue"
            se.from_warehouse     = roll.warehouse
            se.append("items", {
                "item_code":  roll.fabric_item,
                "qty":         used_qty,
                "uom":         "Kg",
                "stock_uom":   "Kg",
                "s_warehouse": roll.warehouse
            })
            se.insert(ignore_permissions=True)
            se.submit()

        # 2) Process each cutting part: receive into stock at zero valuation
        for pr in self.cutting_parts:
            item      = pr.part
            qty       = pr.quantity or 0
            warehouse = pr.warehouse
            if not warehouse:
                frappe.throw(f"Please set a Warehouse on Cutting Part {item}")

            se = frappe.new_doc("Stock Entry")
            se.stock_entry_type          = "Material Receipt"
            se.to_warehouse              = warehouse
            se.allow_zero_valuation_rate = True

            se.append("items", {
                "item_code":                 item,
                "qty":                        qty,
                "uom":                       "Nos",
                "stock_uom":                 "Nos",
                "t_warehouse":               warehouse,
                "allow_zero_valuation_rate": True
            })
            se.insert(ignore_permissions=True)
            se.submit()
