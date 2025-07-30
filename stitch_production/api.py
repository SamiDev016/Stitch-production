# apps/stitch_production/stitch_production/api.py

import frappe
from frappe import _
from frappe.utils import now_datetime


@frappe.whitelist()
def get_boms_from_operation(operation_name):
    try:
        doc = frappe.get_doc("cutting operation", operation_name)
        bom_list = [row.parent_bom for row in doc.parent_boms if row.parent_bom]
        return {"status": "success", "boms": bom_list}
    except Exception as e:
        return {"status": "error", "message": str(e)}





@frappe.whitelist()
def get_post_assembly_by_barcode(barcode):
    docname = frappe.db.get_value("Post Assembly", {"barcode": barcode}, "name")
    if not docname:
        return None

    return frappe.get_doc("Post Assembly", docname)


# @frappe.whitelist()
# def advance_stitching_step(docname):
#     doc = frappe.get_doc("Post Assembly", docname)
#     doc_records = doc.records

#     steps = [
#         {"status": "WIP Stitching", "step_index": 1, "end_step": 0},
#         {"status": "Stitched", "step_index": 1, "end_step": 1},
#         {"status": "WIP Finishing", "step_index": 2, "end_step": 0},
#         {"status": "Finished", "step_index": 2, "end_step": 1},
#         {"status": "WIP Pressing", "step_index": 3, "end_step": 0},
#         {"status": "Pressed", "step_index": 3, "end_step": 1},
#         {"status": "WIP Wrapping", "step_index": 4, "end_step": 0},
#         {"status": "Wrapped", "step_index": 4, "end_step": 1},  
#     ]

#     current_index = len(doc_records)

#     if current_index >= len(steps):
#         return {"message": "Already at final step."}

#     step = steps[current_index]

#     now = now_datetime()
#     new_record = doc.append("records", {})
#     new_record.step_index = step["step_index"]
#     new_record.step = step["status"]

#     if step["end_step"] == 0:
#         new_record.start_time = now
#         new_record.status = step["status"]

#     elif step["end_step"] == 1:
#         last_wip_record = None
#         if doc_records:
#             for r in reversed(doc_records):
#                 if r.step_index == step["step_index"] and r.start_time:
#                     last_wip_record = r
#                     break

#         new_record.end_time = now
#         new_record.start_time = last_wip_record.start_time if last_wip_record else now
#         new_record.duration = (
#             frappe.utils.time_diff_in_seconds(now, new_record.start_time) / 60
#         )
#         new_record.status = step["status"]

#         stitch_settings = frappe.get_single("Stitch Settings")
#         if step["status"] == "Stitched":
#             new_record.expense_account = stitch_settings.stitched_expense_account
#         elif step["status"] == "Finished":
#             new_record.expense_account = stitch_settings.finished_expense_account
#         elif step["status"] == "Pressed":
#             new_record.expense_account = stitch_settings.pressed_expense_account
#         elif step["status"] == "Wrapped":
#             new_record.expense_account = stitch_settings.wrapped_expense_account
        
        

#     doc.status = step["status"]
#     doc.save()

#     if step["status"] == "Wrapped":
#         doc.submit()
#         return {"message": "Final step completed. Document submitted successfully."}

#     return {"message": f"Advanced to step {step['status']}"}

@frappe.whitelist()
def advance_stitching_step(docname, final_qty=None):
    doc = frappe.get_doc("Post Assembly", docname)
    doc_records = doc.records

    steps = [
        {"status": "WIP Stitching", "step_index": 1, "end_step": 0},
        {"status": "Stitched", "step_index": 1, "end_step": 1},
        {"status": "WIP Finishing", "step_index": 2, "end_step": 0},
        {"status": "Finished", "step_index": 2, "end_step": 1},
        {"status": "WIP Pressing", "step_index": 3, "end_step": 0},
        {"status": "Pressed", "step_index": 3, "end_step": 1},
        {"status": "WIP Wrapping", "step_index": 4, "end_step": 0},
        {"status": "Wrapped", "step_index": 4, "end_step": 1}
    ]

    now = now_datetime()

    if len(doc_records) >= len(steps):
        if final_qty:
            if doc.docstatus != 1:
                doc.qty = float(final_qty)
                doc.cost_per_one += frappe.get_single("Stitch Settings").stitched_cost
                doc.total_cost = float(doc.cost_per_one) * doc.qty
                doc.submit()

                stock_entry = frappe.new_doc("Stock Entry")
                stock_entry.stock_entry_type = "Material Receipt"
                target_warehouse = frappe.get_single("Stitch Settings").stitching_finish_warehouse
                stock_entry.append("items", {
                    "item_code": doc.finished,
                    "qty": doc.qty,
                    "basic_rate": doc.cost_per_one,
                    "uom": frappe.db.get_value("Item", doc.finished, "stock_uom"),
                    "conversion_factor": 1,
                    "t_warehouse": target_warehouse
                })
                stock_entry.insert()
                stock_entry.submit()

                return {"message": f"Submitted. Receipt: {stock_entry.name}"}
            else:
                return {"message": "Already submitted."}
        else:
            return {
                "final_step": True,
                "item": doc.finished,
                "qty": doc.qty
            }

    current_index = len(doc_records)
    step = steps[current_index]

    new_record = doc.append("records", {})
    new_record.step_index = step["step_index"]
    new_record.step = step["status"]

    if step["end_step"] == 0:
        new_record.start_time = now
        new_record.status = step["status"]

    elif step["end_step"] == 1:
        last_wip_record = None
        for r in reversed(doc_records):
            if r.step_index == step["step_index"] and r.start_time:
                last_wip_record = r
                break

        new_record.end_time = now
        new_record.start_time = last_wip_record.start_time if last_wip_record else now
        new_record.duration = (
            frappe.utils.time_diff_in_seconds(now, new_record.start_time) / 60
        )
        new_record.status = step["status"]

        stitch_settings = frappe.get_single("Stitch Settings")
        if step["status"] == "Stitched":
            new_record.expense_account = stitch_settings.stitched_expense_account
        elif step["status"] == "Finished":
            new_record.expense_account = stitch_settings.finished_expense_account
        elif step["status"] == "Pressed":
            new_record.expense_account = stitch_settings.pressed_expense_account
        elif step["status"] == "Wrapped":
            new_record.expense_account = stitch_settings.wrapped_expense_account

    doc.status = step["status"]
    doc.save()

    return {"message": f"Advanced to step {step['status']}"}



@frappe.whitelist()
def get_post_assemblies_by_assembly_barcode(barcode):
    assembly = frappe.get_doc("Assemblying", {"barcode": barcode})
    if not assembly:
        return None

    posts = frappe.get_all("Post Assembly",
        filters={"operation": assembly.name},
        fields=["name", "finished", "qty", "barcode", "status"]
    )

    return {
        "assembly": assembly.name,
        "posts": posts
    }
