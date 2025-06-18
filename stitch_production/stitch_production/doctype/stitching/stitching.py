# Copyright (c) 2025, samidev016 and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class Stitching(Document):
	def before_save(self):
		if not self.finish_good or not self.finish_good_qty or not self.batches or self.finish_good_qty <= 0 or not self.finish_good_warehouse:
			frappe.throw(_("Unfilled fields"))
		
		for batch in self.batches:
			if not batch.batch or not batch.existing_qty:
				frappe.throw(_("Unfilled fields"))
			if batch.using_qty <= 0:
				frappe.throw(_("Unfilled fields"))
			if batch.using_qty > batch.existing_qty:
				frappe.throw(_("Using qty cannot be greater than existing qty"))
	
	def on_submit(self):

		se1 = frappe.new_doc("Stock Entry")
		se1.purpose           = se1.stock_entry_type = "Material Receipt"
		se1.company           = frappe.defaults.get_user_default("Company")
		se1.append("items", {
			"item_code": self.finish_good,
			"qty":        self.finish_good_qty,
			"uom":        frappe.db.get_value("Item", self.finish_good, "stock_uom"),
			"t_warehouse": self.finish_good_warehouse,
			"allow_zero_valuation_rate": 1
		})
		se1.insert()
		se1.submit()

		se2 = frappe.new_doc("Stock Entry")
		se2.purpose           = se2.stock_entry_type = "Material Issue"
		se2.company           = frappe.defaults.get_user_default("Company")

		for row in self.batches:
			using_qty = row.using_qty
			pgcd      = row.existing_qty

			pb = frappe.get_doc("Parts Batch", row.batch)
			op = frappe.get_doc("cutting operation", pb.source_operation)
			wh = op.distination_warehouse
			for part_row in pb.parts:
				real_qty = (part_row.qty / pgcd) * using_qty

				se2.append("items", {
					"item_code": part_row.part,
					"qty":        real_qty,
					"uom":        frappe.db.get_value("Item", part_row.part, "stock_uom"),
					"s_warehouse": wh,
					"allow_zero_valuation_rate": 1
				})

				part_row.db_set("qty", part_row.qty - real_qty)

			pb.save()

		se2.insert()
		se2.submit()

		
		
		
			
