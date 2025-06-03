# Purchase Receipt → On Submit

for r in doc.get("custom_rolls", []):
    # Fetch color from Item Variant Attribute
    color = frappe.db.get_value(
        "Item Variant Attribute",
        {"parent": r.fabric_item, "attribute": "Colour"},
        "attribute_value"
    )

    # Fetch the image from the linked Item
    item_image = frappe.db.get_value("Item", r.fabric_item, "image") or ""

    roll = frappe.get_doc({
        "doctype":          "Rolls",
        "fabric_item":      r.fabric_item,
        "supplier":         doc.supplier,
        "warehouse":        r.warehouse,
        "company":          doc.company,
        "weight":           r.weight,
        "price_per_kg":     r.price_per_qty,
        "status":           "New",
        "color":            color or "",
        "longeur":          r.longeur,
        "turbolantouvert":  r.turbolantouvert,
        "gsm":              r.gsm,
        "attache_image":    item_image
    })

    roll.insert(ignore_permissions=True)
