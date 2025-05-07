import frappe
from frappe.model.document import Document

class Rolls(Document):
    def validate(self):
        if not self.serial_number:
            prefix = "ROLL-"
            result = frappe.db.sql(
                """
                SELECT MAX(
                    CAST(
                        SUBSTRING_INDEX(serial_number, '-', -1)
                    AS UNSIGNED)
                )
                FROM `tabRolls`
                WHERE serial_number LIKE %s
                """,
                (prefix + '%',),
                as_list=True
            )
            max_seq = result[0][0] or 0
            next_seq = max_seq + 1
            self.serial_number = f"{prefix}{next_seq:04d}"
            self.serial_number_barcode = f"{prefix}{next_seq:04d}"

