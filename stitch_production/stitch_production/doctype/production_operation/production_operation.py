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
                self.append("raw_materials", {
                    "material":          bi.item_code,
                    "batch_no":          None,
                    "required_quantity": required,
                    "item_warehouse":    bom.fg_warehouse
                })

    def on_submit(self):
        # 1) Create a named batch for the FG
        fg_batch = self._make_named_batch(self.production_item)
        # store it for reference
        self.db_set("finish_good_batch", fg_batch)

        # 2) Build maps for raw materials
        batch_map = {r.material: r.batch_no for r in self.raw_materials}
        qty_map   = {r.material: r.required_quantity for r in self.raw_materials}
        wh_map    = {r.material: r.item_warehouse for r in self.raw_materials}

        # 3) Start the Stock Entry
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

        # 4) Add Finished Good FIRST
        se.append("items", {
            "item_code":         self.production_item,
            "qty":               self.produced_quantity,
            "transfer_qty":      self.produced_quantity,
            "t_warehouse":       self.warehouse,
            "batch_no":          fg_batch,
            "create_new_batch":  1,
            "uom":               frappe.db.get_value("Item", self.production_item, "stock_uom"),
            "conversion_factor": 1
        })

        # 5) Then add each raw-material line
        for mat in batch_map:
            se.append("items", {
                "item_code":         mat,
                "qty":               qty_map[mat],
                "transfer_qty":      qty_map[mat],
                "s_warehouse":       wh_map[mat],
                "batch_no":          batch_map[mat],
                "create_new_batch":  0,
                "uom":               frappe.db.get_value("Item", mat, "stock_uom"),
                "conversion_factor": 1
            })

        # 6) Save & submit
        se.insert(ignore_permissions=True)
        se.submit()

        # 7) Link back
        self.db_set("stock_entry", se.name)

    def _make_named_batch(self, item_code):
        suffix = ''.join(random.choices(string.digits, k=4))
        batch_id = f"Production-{self.name}-{suffix}"
        batch = frappe.get_doc({
            "doctype": "Batch",
            "item":     item_code,
            "batch_id": batch_id
        })
        batch.insert(ignore_permissions=True)
        return batch.name
