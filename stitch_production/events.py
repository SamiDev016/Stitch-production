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


def sync_item_attribute_values(doc, method):
    """
    After saving Item Attribute, copy each row.attribute_value from the child
    table item_attribute_values into the corresponding custom doctype:
      - Item Attribute "Colour" -> DocType "Colour", field "colour"
      - Item Attribute "Size"   -> DocType "Size",   field "size"
    """

    if not getattr(doc, "attribute_name", None):
        return

    attr = (doc.attribute_name or "").strip().lower()
    if attr not in ("size", "colour"):
        return

    mapping = {
        "size":   {"doctype": "Size",   "field": "size"},
        "colour": {"doctype": "Colour", "field": "colour"},
    }

    target = mapping[attr]["doctype"]
    target_field = mapping[attr]["field"]

    if not frappe.db.exists("DocType", target):
        frappe.log_error(f"Sync failed: target doctype '{target}' not found.")
        return

    meta = frappe.get_meta(target)
    if not meta.has_field(target_field):
        frappe.log_error(f"Sync failed: field '{target_field}' not found in '{target}'.")
        return

    rows = frappe.get_all(target, fields=[target_field])
    existing = set([ (r.get(target_field) or "").strip() for r in rows if r.get(target_field) ])

    to_create = []
    for row in doc.get("item_attribute_values") or []:
        val = (row.attribute_value or "").strip()
        if not val:
            continue
        if val not in existing:
            to_create.append(val)
            existing.add(val)

    for val in to_create:
        try:
            new_doc = frappe.new_doc(target)
            new_doc.update({target_field: val})
            new_doc.insert(ignore_permissions=True)
        except Exception:
            frappe.log_error(f"Failed to create {target} record for value: {val}\n{frappe.get_traceback()}")

