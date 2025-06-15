import frappe
from frappe.model.document import Document

class ParentBOM(Document):
    def before_save(self):
        pf_color = frappe.db.get_value(
            "Item Variant Attribute",
            {"parent": self.produit_finis, "attribute": "Colour"},
            "attribute_value"
        )
        pf_size = frappe.db.get_value(
            "Item Variant Attribute",
            {"parent": self.produit_finis, "attribute": "Size"},
            "attribute_value"
        )

        if not pf_color or not pf_size:
            frappe.throw("Produit finis doit avoir à la fois COULEUR et TAILLE")

        raw_map = {}

        for row in self.boms or []:
            if not row.bom:
                continue

            bom_doc = frappe.get_doc("BOM", row.bom)
            for item in bom_doc.items or []:
                template = item.item_code
                qty_per_unit = item.qty or 0
                if not template or qty_per_unit <= 0:
                    continue

                variants = frappe.get_all(
                    "Item",
                    filters={"variant_of": template, "disabled": 0},
                    fields=["name"]
                )

                for v in variants:
                    v_color = frappe.db.get_value(
                        "Item Variant Attribute",
                        {"parent": v.name, "attribute": "Colour"},
                        "attribute_value"
                    )
                    v_size = frappe.db.get_value(
                        "Item Variant Attribute",
                        {"parent": v.name, "attribute": "Size"},
                        "attribute_value"
                    )

                    if v_color == pf_color and v_size == pf_size:
                        raw_map[v.name] = raw_map.get(v.name, 0) + qty_per_unit

        self.set("raw_materials", [])
        for part_name, total_qty in raw_map.items():
            row = self.append("raw_materials", {})
            row.part = part_name
            row.qty = total_qty
