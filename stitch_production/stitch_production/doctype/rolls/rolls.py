import frappe
from frappe.model.document import Document

class Rolls(Document):
    def on_submit(self):
        # 1. Validate that a fabric item is linked
        if not self.fabric_item:
            frappe.throw("Cannot generate Serial Number: Fabric Item is required.", frappe.MandatoryError)

        # 2. Load the Item document for the linked fabric_item
        try:
            item = frappe.get_doc("Item", self.fabric_item)
        except frappe.DoesNotExistError:
            frappe.throw(f"Cannot generate Serial Number: Fabric Item '{self.fabric_item}' not found.", frappe.DoesNotExistError)

        # 3. Determine the fabric/item name for the prefix
        #    Use variant_name if it exists, otherwise item_name
        fabric_name = item.variant_name or item.item_name or item.name
        if not fabric_name:
            frappe.throw("Cannot generate Serial Number: Fabric item has no name.", frappe.ValidationError)

        # 4. Construct the prefix for the serial number
        prefix = f"ROLL-{fabric_name}-"

        # 5. Query the maximum existing numeric suffix for this fabric
        #    Convert the trailing part to integer to find the max sequence
        like_pattern = prefix + "%"  # e.g., "ROLL-Cotton-%" 
        result = frappe.db.sql("""
            SELECT MAX(CAST(SUBSTRING_INDEX(serial_number, '-', -1) AS UNSIGNED))
            FROM `tabRolls`
            WHERE fabric_item = %s AND serial_number LIKE %s
        """, (self.fabric_item, like_pattern))

        max_seq = result[0][0] if result and result[0][0] else 0
        next_seq = (max_seq or 0) + 1

        # 6. Format the next sequence as four digits
        serial_number = f"{prefix}{next_seq:04d}"

        # 7. Ensure the generated serial is unique (handle any collisions)
        #    If the serial exists, keep incrementing
        while frappe.db.exists("Rolls", {"serial_number": serial_number}):
            next_seq += 1
            serial_number = f"{prefix}{next_seq:04d}"

        # 8. Update the document’s serial_number field in the database
        #    Use db_set since the document is being submitted (docstatus=1)
        self.db_set("serial_number", serial_number)

