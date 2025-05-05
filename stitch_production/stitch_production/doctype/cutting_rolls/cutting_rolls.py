# apps/stitch_production/stitch_production/doctype/cutting_rolls/cutting_rolls.py

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

class CuttingRolls(Document):
    def validate(self):
        # 1) default used_qty to the roll's full weight if not set
        if self.roll and (self.used_qty is None or not flt(self.used_qty)):
            # grab the roll's current weight
            weight = flt(frappe.db.get_value("Rolls", self.roll, "weight") or 0)
            self.used_qty = weight

        # 2) ensure they still don't exceed it
        self._validate_used_qty()

    def _validate_used_qty(self):
        if self.roll and self.used_qty is not None:
            available = flt(frappe.db.get_value("Rolls", self.roll, "weight") or 0)
            used      = flt(self.used_qty)
            if used > available:
                frappe.throw(
                    _("You tried to use {0} kg but Roll {1} only has {2} kg left.")
                    .format(used, self.roll, available),
                    title=_("Quantity Exceeds Available")
                )

