# before cancel

# Purchase Receipt → Before Cancel

# For each entry in custom_rolls, find and delete matching Rolls record(s)
for r in doc.get("custom_rolls", []):
    filters = {
        "fabric_item":       r.fabric_item,
        "supplier":          doc.supplier,
        "warehouse":         r.warehouse,
        "weight":            r.weight,
        "price_per_kg":      r.price_per_qty,
        "company":           doc.company,
        "longeur":           r.longeur,
        "turbolantouvert":   r.turbolantouvert,
        "gsm":               r.gsm
    }
    rolls_to_delete = frappe.get_all("Rolls", filters=filters, pluck="name")

    for roll_name in rolls_to_delete:
        frappe.get_doc("Rolls", roll_name).delete(ignore_permissions=True)
