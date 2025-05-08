# Copyright (c) 2025, samidev016 and contributors
# For license information, please see license.txt

# import frappe
import frappe
from frappe.model.document import Document
from frappe import _

class ProductionOperation(Document):

    def validate(self):
        # 1) Ensure BOM and quantity are provided
        if not self.poduction_bom:
            frappe.throw(_("Please select a Production BOM"))
        if not self.produced_quantity:
            frappe.throw(_("Please enter a quantity to produce"))

        # 2) Load the BOM to pull its production_item
        bom = frappe.get_doc("BOM", self.poduction_bom)
        self.production_item = bom.item

        # 3) If raw_materials is empty, pre-fill one line per BOM item
        if not self.raw_materials:
            for bi in bom.items:
                # Scale BOM qty by your produced_qty
                required = (bi.qty or 0) * self.produced_quantity / (bom.quantity or 1)
                self.append("raw_materials", {
                    "material":     bi.item_code,
                    "batch_no":     None,         # user picks which batch
                    "required_quantity": required
                })

    def on_submit(self):
        # Build lookup maps from your child table
        batch_map = { r.material: r.batch_no     for r in self.raw_materials }
        qty_map   = { r.material: r.required_quantity for r in self.raw_materials }

        # Create the Manufacture Stock Entry
        se = frappe.new_doc("Stock Entry")
        se.stock_entry_type = "Manufacture"
        se.bom_no           = self.poduction_bom
        se.production_item  = self.production_item
        se.produced_qty     = self.produced_quantity
        se.fg_warehouse     = self.warehouse

        # Tell ERPNext to pull in BOM lines automatically
        se.run_method("get_items")

        # Override each raw-material line with the exact batch & qty
        for line in se.items:
            mat = line.item_code
            if mat in batch_map:
                line.batch_no     = batch_map[mat]
                line.transfer_qty = qty_map[mat]
                # set source warehouse from the Batch record
                line.s_warehouse  = frappe.db.get_value("Batch", batch_map[mat], "warehouse")

        # Save & submit the Stock Entry
        se.insert(ignore_permissions=True)
        se.submit()

        # Optionally store a link back to the SE on your operation
        self.db_set("stock_entry", se.name)

