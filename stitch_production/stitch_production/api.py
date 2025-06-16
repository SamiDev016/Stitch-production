import frappe
from frappe import _

@frappe.whitelist()
def get_boms_for_cutting_operation(operation_name):
    """Return list of BOM names linked to a cutting operation."""
    if not operation_name:
        return []

    try:
        op_doc = frappe.get_doc("cutting operation", operation_name)
        bom_names = []

        for row in op_doc.parent_boms or []:
            if row.parent_bom:
                if frappe.db.exists("BOM", row.parent_bom):
                    bom_names.append(row.parent_bom)

        return bom_names
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "get_boms_for_cutting_operation Error")
        return []
