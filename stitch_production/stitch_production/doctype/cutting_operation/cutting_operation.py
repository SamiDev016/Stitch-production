import frappe
from frappe.model.document import Document
from frappe.exceptions import DoesNotExistError

class cuttingoperation(Document):
    def validate(self):
        total_ws = 0.0
        for ws in self.get("workstation_cost", []):
            cost = (ws.cost_per_hour or 0) * (ws.total_hours or 0)
            total_ws += cost
            frappe.logger().info(f"Workstation: {ws.workstation_name}, Cost: {cost}")

        total_wr = 0.0
        for wr in self.get("worker_cost", []):
            cost = (wr.cost_per_hour or 0) * (wr.total_hours or 0)
            total_wr += cost
            frappe.logger().info(f"Worker: {wr.worker}, Cost: {cost}")

        individual = self.individual_cost or 0
        frappe.logger().info(f"Individual Cost: {individual}")

        self.total_cost = total_ws + total_wr + individual

    def on_submit(self):
        for row in self.used_rolls:
            # 1. Load and validate the existing Rolls record
            try:
                roll = frappe.get_doc("Rolls", row.roll)
            except DoesNotExistError:
                frappe.throw(f"Roll {row.roll} not found")

            used_qty = row.used_qty or 0.0
            if roll.weight < used_qty:
                frappe.throw(
                    f"Used quantity ({used_qty} Kg) exceeds available weight ({roll.weight} Kg) for Roll {roll.name}"
                )

            # 2. Directly decrement the roll's weight
            roll.weight = roll.weight - used_qty
            roll.save(ignore_permissions=True)

            # 3. Create a Material Issue Stock Entry for the used fabric
            se = frappe.new_doc("Stock Entry")
            se.stock_entry_type = "Material Issue"
            se.from_warehouse = roll.warehouse
            se.append("items", {
                "item_code": roll.fabric_item,
                "qty": used_qty,
                "uom": "Kg",
                "stock_uom": "Kg",
                "s_warehouse": roll.warehouse
            })
            se.insert(ignore_permissions=True)
            se.submit()
