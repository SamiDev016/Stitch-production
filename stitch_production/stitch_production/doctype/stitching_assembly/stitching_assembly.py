from frappe.model.document import Document
import frappe

class StitchingAssembly(Document):
    def before_save(self):
        cutting_boms = {}

        main_op_doc = frappe.get_doc("cutting operation", self.main_operation)
        for row in main_op_doc.parent_boms or []:
            if not row.parent_bom:
                continue
            bom_doc = frappe.get_doc("BOM", row.parent_bom)
            cutting_boms[bom_doc.name] = bom_doc

        frappe.msgprint(f"cutting_boms: {list(cutting_boms.keys())}")

        parent_boms = {}
        parent_bom_doc = frappe.get_doc("Parent BOM", self.parent_bom)
        for bom in parent_bom_doc.boms or []:
            if not bom.bom:
                continue
            bom_doc = frappe.get_doc("BOM", bom.bom)
            parent_boms[bom_doc.name] = bom_doc

        frappe.msgprint(f"parent_boms: {list(parent_boms.keys())}")

        missing_boms = []
        for bom in cutting_boms:
            if bom not in parent_boms:
                missing_boms.append(bom)

        if missing_boms:
            frappe.throw(f"Les BOMs suivants de l'opération de coupe ne sont pas présents dans le Parent BOM sélectionné : {', '.join(missing_boms)}")

        main_batches = {}
        for batch in frappe.get_all("Parts Batch", filters={
            "source_bom": ["in", list(cutting_boms.keys())],
            "source_operation": self.main_operation,
        }):
            main_batches[batch.name] = batch

        frappe.msgprint(f"main_batches: {list(main_batches.keys())}")




        remaining_batches = {}
        #missing boms
        for bom in missing_boms:
            for batch in frappe.get_all("Parts Batch", filters={
                "source_bom": bom,
            }):
                remaining_batches[batch.name] = batch
		
        frappe.msgprint(f"remaining_batches: {list(remaining_batches.keys())}")
