import frappe
from frappe.model.document import Document
from frappe import _
import random
import string

class ProductionOperation(Document):

    def validate(self):
        if not self.poduction_bom:
            frappe.throw(_("Please select a Production BOM"))
        if not self.produced_quantity:
            frappe.throw(_("Please enter a quantity to produce"))

        bom = frappe.get_doc("BOM", self.poduction_bom)
        self.production_item = bom.item

        if not self.raw_materials:
            for bi in bom.items:
                required = (bi.qty or 0) * self.produced_quantity / (bom.quantity or 1)
                # user will pick batch_no & item_warehouse in the form
                self.append("raw_materials", {
                    "material": bi.item_code,
                    "batch_no": None,
                    "required_quantity": required,
                    "item_warehouse": bom.fg_warehouse
                })

    def on_submit(self):
        # Create a random batch for the finished good
        fg_batch = self._make_random_batch(self.production_item)
        # Store in your new read-only field
        self.db_set("finish_good_batch", fg_batch)

        # Build maps from raw_materials table
        batch_map = {r.material: r.batch_no for r in self.raw_materials}
        qty_map   = {r.material: r.required_quantity for r in self.raw_materials}
        wh_map    = {r.material: r.item_warehouse for r in self.raw_materials}

        # Create Stock Entry header
        se = frappe.new_doc("Stock Entry")
        se.update({
            "stock_entry_type":   "Manufacture",
            "bom_no":             self.poduction_bom,
            "production_item":    self.production_item,
            "produced_qty":       self.produced_quantity,
            "fg_completed_qty":   self.produced_quantity,
            "fg_warehouse":       self.warehouse,
            "from_bom":           1
        })

        # 1) Finished Good line (with random batch)
        se.append("items", {
            "item_code":     self.production_item,
            "qty":           self.produced_quantity,
            "t_warehouse":   self.warehouse,
            "batch_no":      fg_batch,
            "uom":           frappe.db.get_value("Item", self.production_item, "stock_uom"),
            "conversion_factor": 1
        })

        # 2) Raw Material lines
        for item_code in batch_map:
            se.append("items", {
                "item_code":    item_code,
                "qty":          qty_map[item_code],
                "transfer_qty": qty_map[item_code],
                "s_warehouse":  wh_map[item_code],
                "batch_no":     batch_map[item_code],
                "uom":          frappe.db.get_value("Item", item_code, "stock_uom"),
                "conversion_factor": 1
            })

        # Insert & submit
        se.insert(ignore_permissions=True)
        se.submit()

        # Link back
        self.db_set("stock_entry", se.name)

    def _make_random_batch(self, item_code):
        rand = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
        batch_id = f"{item_code}-{rand}"
        b = frappe.get_doc({
            "doctype": "Batch",
            "item": item_code,
            "batch_id": batch_id
        })
        b.insert(ignore_permissions=True)
        return b.name
