import frappe
from frappe.model.document import Document

class ParentBOM(Document):
    def before_save(self):
        raw_map = {}

        for row in self.boms or []:
            if not row.bom:
                continue

            bom_doc = frappe.get_doc("BOM", row.bom)
            for item in bom_doc.items or []:
                template = item.item_code
                quantity = item.qty or 0
                if not template or quantity <= 0:
                    continue

                variants = frappe.get_all(
                    "Item",
                    filters={"variant_of": template, "disabled": 0},
                    fields=["name"]
                )
                for v in variants:
                    part_name = v.name
                    raw_map[part_name] = raw_map.get(part_name, 0) + quantity

        parent_bom_doc = frappe.get_doc("BOM", self.parent_bom)
        for raw in parent_bom_doc.items or []:
            if not raw.item_code:
                continue
            template_p = raw.item_code
            quantity_p = raw.qty or 0
            if not template_p or quantity_p <= 0:
                continue
            variants_p = frappe.get_all(
                "Item",
                filters={"variant_of" : template_p, "disabled" : 0},
                fields=["name"]
            )
            for v in variants_p:
                part_name_p = v.name
                raw_map[part_name_p] = raw_map.get(part_name_p, 0) + quantity_p
    
        self.set("raw_materials", [])
        for part, qty in raw_map.items():
            row = self.append("raw_materials", {})
            row.part = part
            row.qty = qty

