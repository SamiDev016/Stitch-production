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


    def on_submit(self):
        if not self.finish_goods or not self.other_batches or not self.main_batches:
            frappe.throw("No finish goods found.")

        company = frappe.defaults.get_user_default("Company")

        # 1) Create Stock Entry
        issue = frappe.new_doc("Stock Entry")
        issue.purpose = issue.stock_entry_type = "Material Issue"
        issue.company = company

        def add_item(item_code, qty, warehouse):
            uom = frappe.db.get_value("Item", item_code, "stock_uom")
            issue.append("items", {
                "item_code": item_code,
                "qty": qty,
                "uom": uom,
                "stock_uom": uom,
                "conversion_factor": 1,
                "s_warehouse": warehouse
            })

        main_consumption = [] 
        for mb in self.main_batches:
            mb_doc = frappe.get_doc("Parts Batch", mb.batch)
            wh = frappe.get_doc("cutting operation", mb_doc.source_operation).distination_warehouse

            qtys = [p.qty for p in mb_doc.parts if p.qty and p.qty > 0]
            ints = [int(q) for q in qtys if float(q).is_integer()]
            pgcd = reduce(math.gcd, ints) if ints else 1

            for p in mb_doc.parts:
                if p.qty and pgcd > 0:
                    to_consume = (p.qty / pgcd) * mb.parts_qty
                    add_item(p.part, to_consume, wh)
                    main_consumption.append((mb.batch, p.part, to_consume))

        other_consumption = [] 
        for ob in self.other_batches:
            ob_doc = frappe.get_doc("Parts Batch", ob.batch)
            wh = frappe.get_doc("cutting operation", ob_doc.source_operation).distination_warehouse

            qtys = [p.qty for p in ob_doc.parts if p.qty and p.qty > 0]
            ints = [int(q) for q in qtys if float(q).is_integer()]
            pgcd = reduce(math.gcd, ints) if ints else 1

            for p in ob_doc.parts:
                if p.qty and pgcd > 0:
                    to_consume = (p.qty / pgcd) * ob.qty
                    add_item(p.part, to_consume, wh)
                    other_consumption.append((ob.batch, p.part, to_consume))

        if issue.items:
            issue.insert()
            issue.submit()
            self.db_set("stock_entry_name", issue.name)
        else:
            frappe.throw("No items were added to the Stock Entry.")

        # ↓ Update child table qty via direct DB update
        for batch_name, part_code, qty_used in main_consumption:
            pb = frappe.get_doc("Parts Batch", batch_name)
            for row in pb.parts:
                if row.part == part_code:
                    new_qty = (row.qty or 0) - qty_used
                    frappe.db.set_value("Parts", row.name, "qty", new_qty)

        for batch_name, part_code, qty_used in other_consumption:
            pb = frappe.get_doc("Parts Batch", batch_name)
            for row in pb.parts:
                if row.part == part_code:
                    new_qty = (row.qty or 0) - qty_used
                    frappe.db.set_value("Parts", row.name, "qty", new_qty)
