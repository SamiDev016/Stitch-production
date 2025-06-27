import frappe
from frappe.model.document import Document
import math
from functools import reduce

class Assemblying(Document):
    def before_save(self):
        batch_names = frappe.get_all(
            "Parts Batch",
            filters={
                "source_operation": self.main_operation,
                "source_bom": self.main_bom
            },
            fields=["name", "batch_name", "color", "size"]
        )

        if not batch_names:
            frappe.throw("No Parts Batch found for those criteria.")

        self.set("main_batches", [])
        self.set("other_batches", [])

        for pb in batch_names:
            batch_doc = frappe.get_doc("Parts Batch", pb["name"])
            qtys = [p.qty for p in batch_doc.parts if p.qty and p.qty > 0.0]
            qtys_int = [int(q) for q in qtys if float(q).is_integer()]
            pgcd = reduce(math.gcd, qtys_int) if qtys_int else 0

            self.append("main_batches", {
                "batch": pb["batch_name"],
                "color": pb["color"],
                "size": pb["size"],
                "parts_qty": pgcd
            })

        if not self.parent_bom:
            frappe.throw("Parent BOM not set")

        p_doc = frappe.get_doc("Parent BOM", self.parent_bom)
        other_boms = [b.bom for b in p_doc.boms if b.bom != self.main_bom]
        frappe.msgprint(f"Other BOMs: {other_boms}")

        for main_batch in self.main_batches:
            color = main_batch.color
            size = main_batch.size
            required_qty = main_batch.parts_qty
            main_batch_name = main_batch.batch

            frappe.msgprint(f"→ Matching for {main_batch_name} (Needed {required_qty})")

            for bom in other_boms:
                accumulated_qty = 0
                selected = []

                other_batches = frappe.get_all(
                    "Parts Batch",
                    filters={
                        "source_bom": bom,
                        "color": color,
                        "size": size
                    },
                    fields=["name", "batch_name"]
                )

                for ob in other_batches:
                    if accumulated_qty >= required_qty:
                        break

                    ob_doc = frappe.get_doc("Parts Batch", ob.name)
                    qtys = [p.qty for p in ob_doc.parts if p.qty and p.qty > 0.0]
                    qtys_int = [int(q) for q in qtys if float(q).is_integer()]
                    pgcd = reduce(math.gcd, qtys_int) if qtys_int else 0

                    if pgcd > 0:
                        take_qty = min(pgcd, required_qty - accumulated_qty)
                        accumulated_qty += take_qty
                        selected.append({
                            "batch": ob.batch_name,
                            "bom": bom,
                            "used_qty": take_qty,
                            "available_qty": pgcd
                        })

                        self.append("other_batches", {
                            "batch": ob.batch_name,
                            "qty": take_qty
                        })

                frappe.msgprint(f"  → {bom}: {selected}")

                if accumulated_qty < required_qty:
                    frappe.throw(
                        f"Not enough parts for BOM <b>{bom}</b> with color <b>{color}</b> and size <b>{size}</b> "
                        f"(Needed: {required_qty}, Found: {accumulated_qty}) for main batch <b>{main_batch_name}</b>"
                    )
        self.set("finish_goods", [])
        template = p_doc.produit_finis

        variants = frappe.get_all(
            "Item",
            filters={
                "variant_of": template,
                "disabled": 0
            },
            fields=["name", "item_code"]
        )

        frappe.msgprint(f"Variants: {variants}")

        for batch in self.main_batches:
            color = batch.color.strip().lower()
            size = batch.size.strip().lower()
            matched_variant = None

            for v in variants:
                attributes = frappe.get_all(
                    "Item Variant Attribute",
                    filters={"parent": v.name},
                    fields=["attribute", "attribute_value"]
                )

                has_color = any(attr.attribute == "Colour" and attr.attribute_value.strip().lower() == color for attr in attributes)
                has_size  = any(attr.attribute == "Size" and attr.attribute_value.strip().lower() == size for attr in attributes)

                if has_color and has_size:
                    matched_variant = v.item_code
                    break

            if matched_variant:
                self.append("finish_goods", {
                    "item": matched_variant,
                    "qty": batch.parts_qty
                })
            else:
                frappe.throw(f"No variant found for color <b>{batch.color}</b> and size <b>{batch.size}</b>.")
