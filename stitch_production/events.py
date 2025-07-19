import frappe

def handle_batch_created(doc, method=None):
    if doc.reference_doctype == "Purchase Receipt" and doc.reference_name:
        pr = frappe.get_doc("Purchase Receipt", doc.reference_name)

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

