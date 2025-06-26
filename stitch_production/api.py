# apps/stitch_production/stitch_production/api.py

import frappe
from frappe import _

@frappe.whitelist()
def get_boms_from_operation(operation_name):
    try:
        doc = frappe.get_doc("cutting operation", operation_name)
        bom_list = [row.parent_bom for row in doc.parent_boms if row.parent_bom]
        return {"status": "success", "boms": bom_list}
    except Exception as e:
        return {"status": "error", "message": str(e)}
