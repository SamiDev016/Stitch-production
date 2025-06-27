import frappe
from frappe.model.document import Document

class ParentBOM(Document):
    def before_save(self):
        bom_finishgood = []

        for bom_row in self.boms:
            if not bom_row.bom:
                continue

            bom_doc = frappe.get_doc("BOM", bom_row.bom)
            items_list = []

            for item in bom_doc.get("items", []):  # ✅ FIXED HERE
                if not item.item_code:
                    continue
                items_list.append({
                    "item_code": item.item_code,
                    "qty": item.qty
                })

            bom_finishgood.append({
                "bom": bom_row.bom,
                "items": items_list
            })

        #frappe.msgprint(f"map bom finish good {bom_finishgood}")

        self.set("raw_materials", [])  # Clear child table properly
        for bom in bom_finishgood:
            for item in bom["items"]:
                self.append("raw_materials", {
                    "item": item["item_code"],
                    "qty": item["qty"],
                    "bom": bom["bom"]
                })
