import frappe

def handle_batch_created(doc, method=None):
    if doc.reference_doctype == "Purchase Receipt" and doc.reference_name:
        pr = frappe.get_doc("Purchase Receipt", doc.reference_name)
        if pr.custom_is_rolls_purchase == 1:
            for pr_item in pr.items:
                if pr_item.item_code == doc.item:
                    rolls = frappe.get_all("Rolls", 
                        filters={
                            "purchase_receipt_link": pr.name,
                            "fabric_item": doc.item
                        },
                        fields=["name", "price_per_kg", "warehouse"]
                    )

                    for roll in rolls:
                        if abs(roll.price_per_kg - pr_item.rate) < 0.001 and roll.warehouse == pr_item.warehouse:
                            frappe.db.set_value("Rolls", roll.name, "batch_number", doc.name)


def handle_batch_created_cutting(doc, method=None):
    if doc.reference_doctype == "Stock Entry" and doc.reference_name:
        stock_entry = frappe.get_doc("Stock Entry", doc.reference_name)
        if stock_entry.stock_entry_type != "Material Receipt" or not stock_entry.get("custom_is_from_cutting"):
            return

        for item in stock_entry.items:
            if item.item_code != doc.item:
                continue

            parts_batches = frappe.get_all(
                "Parts Batch",
                filters={"docstatus": 1},
                fields=["name"],
                order_by="creation desc"
            )

            for pb in parts_batches:
                parts_batch = frappe.get_doc("Parts Batch", pb.name)

                for part_row in parts_batch.parts:
                    if (
                        part_row.part == item.item_code
                        and not part_row.get("batch_number")
                        and abs((part_row.qty or 0) - (item.qty or 0)) < 0.001
                    ):
                        part_row.batch_number = doc.name
                        parts_batch.save()
                        frappe.db.commit()
                        return






# def handle_batch_created_cutting(doc, method=None):
#     if doc.reference_doctype == "Stock Entry" and doc.reference_name:
#         stock_entry = frappe.get_doc("Stock Entry", doc.reference_name)

#         if stock_entry.stock_entry_type != "Material Receipt":
#             return

#         cutting_op = frappe.get_value(
#             "cutting operation",
#             {"receipt_entry_name": stock_entry.name},
#             "name"
#         )

#         if not cutting_op:
#             return

#         for item in stock_entry.items:
#             if item.item_code != doc.item:
#                 continue

#             parts_batches = frappe.get_all(
#                 "Parts Batch",
#                 filters={
#                     "docstatus": 1,
#                     "source_operation": cutting_op
#                 },
#                 fields=["name"]
#             )

#             for pb in parts_batches:
#                 parts_batch = frappe.get_doc("Parts Batch", pb.name)
#                 for part_row in parts_batch.parts:
#                     if (
#                         part_row.part == item.item_code
#                         and not part_row.get("batch_number")
#                         and abs((part_row.qty or 0) - (item.qty or 0)) < 0.001
#                     ):
#                         part_row.batch_number = doc.name
#                         parts_batch.save()
#                         frappe.db.commit()
#                         return


