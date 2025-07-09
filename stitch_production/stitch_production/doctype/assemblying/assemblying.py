import frappe
from frappe.model.document import Document
import math
from functools import reduce


def generate_barcode(name, index):
    return f"{name}-{str(index).zfill(2)}"


class Assemblying(Document):
    def before_save(self):
        if not self.special_assembly:
            self.handle_normal_assembly()
        else:
            self.handle_special_assembly()

    def handle_normal_assembly(self):
        frappe.msgprint("🔄 Starting normal assembly handling...")

        batch_names = frappe.get_all(
            "Parts Batch",
            filters={"source_operation": self.main_operation, "source_bom": self.main_bom},
            fields=["name", "batch_name", "color", "size"]
        )

        if not batch_names:
            frappe.throw("No Parts Batch found for those criteria.")

        self.set("main_batches", [])
        self.set("other_batches", [])

        for idx, pb in enumerate(batch_names):
            batch_doc = frappe.get_doc("Parts Batch", pb["name"])
            qtys = [p.qty for p in batch_doc.parts if p.qty and p.qty > 0.0]
            qtys_int = [int(q) for q in qtys if float(q).is_integer()]
            pgcd = reduce(math.gcd, qtys_int) if qtys_int else 0

            frappe.msgprint(f"📦 Main Batch: {pb['batch_name']} | PGCD: {pgcd}")

            self.append("main_batches", {
                "batch": pb["batch_name"],
                "color": pb["color"],
                "size": pb["size"],
                "parts_qty": pgcd,
                "finish_good_index": idx
            })

        if not self.parent_bom:
            frappe.throw("Parent BOM not set")

        p_doc = frappe.get_doc("Parent BOM", self.parent_bom)
        other_boms = [b.bom for b in p_doc.boms if b.bom != self.main_bom]

        for main_batch in self.main_batches:
            color = main_batch.color
            size = main_batch.size
            required_qty = main_batch.parts_qty
            main_batch_name = main_batch.batch

            frappe.msgprint(f"🔎 Processing main batch {main_batch_name} | Needed Qty: {required_qty}")

            for bom in other_boms:
                accumulated_qty = 0
                selected = []

                other_batches = frappe.get_all(
                    "Parts Batch",
                    filters={"source_bom": bom, "color": color, "size": size},
                    fields=["name", "batch_name"]
                )

                for ob in other_batches:
                    if accumulated_qty >= required_qty:
                        break

                    ob_doc = frappe.get_doc("Parts Batch", ob.name)
                    qtys = [p.qty for p in ob_doc.parts if p.qty and p.qty > 0.0]
                    qtys_int = [int(q) for q in qtys if float(q).is_integer()]
                    pgcd = reduce(math.gcd, qtys_int) if qtys_int else 0

                    frappe.msgprint(f"📄 Other Batch: {ob.batch_name} | PGCD: {pgcd}")

                    if pgcd > 0:
                        take_qty = min(pgcd, required_qty - accumulated_qty)
                        frappe.msgprint(f"✅ Using {take_qty} from {ob.batch_name} for BOM {bom}")

                        accumulated_qty += take_qty
                        selected.append({
                            "batch": ob.batch_name,
                            "bom": bom,
                            "used_qty": take_qty,
                            "available_qty": pgcd
                        })

                        self.append("other_batches", {
                            "batch": ob.batch_name,
                            "qty": take_qty,
                            "finish_good_index": main_batch.finish_good_index
                        })

                if accumulated_qty < required_qty:
                    frappe.throw(
                        f"❌ Not enough parts for BOM <b>{bom}</b> with color <b>{color}</b> and size <b>{size}</b>. "
                        f"Needed: {required_qty}, Found: {accumulated_qty} for main batch <b>{main_batch_name}</b>"
                    )

        self.set("finish_goods", [])
        template = p_doc.produit_finis

        variants = frappe.get_all(
            "Item",
            filters={"variant_of": template, "disabled": 0},
            fields=["name", "item_code"]
        )

        fg_idx = 0

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
                has_size = any(attr.attribute == "Size" and attr.attribute_value.strip().lower() == size for attr in attributes)

                if has_color and has_size:
                    matched_variant = v.item_code
                    break

            if matched_variant:
                barcode = generate_barcode(self.name, fg_idx)
                self.append("finish_goods", {
                    "item": matched_variant,
                    "qty": batch.parts_qty,
                    "barcode": barcode,
                    "color": color,
                    "size": size,
                    "finish_good_index": fg_idx
                })
                frappe.msgprint(f"🎯 Matched Variant: {matched_variant} | Qty: {batch.parts_qty}")
            else:
                frappe.throw(f"No variant found for color <b>{batch.color}</b> and size <b>{batch.size}</b>.")
            fg_idx += 1

        # 🔢 Cost Calculation
        total_cost = 0.0
        total_cost_without_parts = 0.0
        self.parts_cost = 0.0
        individual_cost = self.individual_cost or 0.0
        workers_total_cost = 0.0

        for w in self.workers or []:
            if not w.worker:
                continue
            emp = frappe.get_doc("Employee", w.worker)
            rate = (emp.ctc or 0) / 22 / 8
            w.hourly_rate = rate
            w.employee_cost = rate * (w.total_hours or 0)
            workers_total_cost += w.employee_cost
            total_cost += w.employee_cost
            total_cost_without_parts += w.employee_cost

        total_cost_without_parts += individual_cost
        self.total_cost_without_parts = total_cost_without_parts
        self.workers_total_cost = workers_total_cost

        parts_cost = 0.0
        for batch in self.main_batches + self.other_batches:
            batch_doc = frappe.get_doc("Parts Batch", batch.batch)
            pgcd = reduce(math.gcd, [int(p.qty) for p in batch_doc.parts if p.qty and float(p.qty).is_integer()])
            if not pgcd:
                continue

            total_batch_cost = 0.0
            multiplier = batch.parts_qty if hasattr(batch, 'parts_qty') else batch.qty

            for p in batch_doc.parts:
                if not p.qty or not p.cost_per_one:
                    continue
                unit_ratio = p.qty / pgcd
                used_qty = unit_ratio * multiplier
                cost = used_qty * p.cost_per_one
                total_batch_cost += cost

                frappe.msgprint(f"💰 Part: {p.part} | Qty: {p.qty} | Reserved: {p.reserved_qty} | PGCD: {pgcd} | Unit Ratio: {unit_ratio} | Used: {used_qty} | Cost: {cost}")

            batch.cost = total_batch_cost
            parts_cost += total_batch_cost

        self.parts_cost = parts_cost

        for fg in self.finish_goods:
            color = fg.color.strip().lower()
            size = fg.size.strip().lower()
            cost = 0.0

            for mb in self.main_batches:
                if mb.color.strip().lower() == color and mb.size.strip().lower() == size:
                    cost += mb.cost
            for ob in self.other_batches:
                ob_doc = frappe.get_doc("Parts Batch", {"batch_name": ob.batch})
                if ob_doc.color.strip().lower() == color and ob_doc.size.strip().lower() == size:
                    cost += ob.cost

            fg.cost = cost
            fg.cost_per_one = cost / fg.qty
            total_qty = sum(fg_item.qty for fg_item in self.finish_goods)
            fg.cost_per_one_adding_assemblying = fg.cost_per_one + (self.total_cost_without_parts / total_qty)
            fg.total_finish_good_adding_assemblying = fg.cost_per_one_adding_assemblying * fg.qty

        self.total_cost = total_cost + individual_cost + parts_cost

    def handle_special_assembly(self):
        total_cost = 0.0
        total_cost_without_parts = 0.0
        self.parts_cost = 0.0
        individual_cost = self.individual_cost or 0.0
        workers_total_cost = 0.0

        for w in self.workers or []:
            if not w.worker:
                continue
            emp = frappe.get_doc("Employee", w.worker)
            rate = (emp.ctc or 0) / 22 / 8
            w.hourly_rate = rate
            w.employee_cost = rate * (w.total_hours or 0)
            workers_total_cost += rate * (w.total_hours or 0)
            total_cost += rate * (w.total_hours or 0)
            total_cost_without_parts += rate * (w.total_hours or 0)

        parts_cost = 0.0
        total_cost_without_parts += individual_cost
        self.total_cost_without_parts = total_cost_without_parts
        self.workers_total_cost = workers_total_cost


        main_color = None
        for row in frappe.get_doc("Custom BOM", self.custom_bom).boms:
            if row.bom == self.main_bom:
                main_color = row.color
                break

        if not main_color:
            frappe.throw(f"Color for BOM {self.main_bom} not found in custom_bom {self.custom_bom}")

        batch_names = frappe.get_all(
            "Parts Batch",
            filters={
                "source_operation": self.main_operation,
                "source_bom": self.main_bom,
                "color": main_color
            },
            fields=["name", "batch_name", "color", "size"]
        )

        if not batch_names:
            frappe.throw("No Parts Batch found for those criteria.")

        self.set("main_batches", [])
        self.set("other_batches", [])

        for idx, pb in enumerate(batch_names):
            batch_doc = frappe.get_doc("Parts Batch", pb["name"])
            qtys = [p.qty for p in batch_doc.parts if p.qty and p.qty > 0.0]
            qtys_int = [int(q) for q in qtys if float(q).is_integer()]
            pgcd = reduce(math.gcd, qtys_int) if qtys_int else 0

            self.append("main_batches", {
                "batch": pb["batch_name"],
                "color": pb["color"],
                "size": pb["size"],
                "parts_qty": pgcd,
                "finish_good_index": idx
            })

        if not self.custom_bom:
            frappe.throw("Custom BOM not set")

        c_bom = frappe.get_doc("Custom BOM", self.custom_bom)
        other_boms = [b.bom for b in c_bom.boms if b.bom != self.main_bom]

        for main_batch in self.main_batches:
            color = main_batch.color
            size = main_batch.size
            required_qty = main_batch.parts_qty
            main_batch_name = main_batch.batch

            for bom in other_boms:
                bom_color = None
                for row in c_bom.boms:
                    if row.bom == bom:
                        bom_color = row.color
                        break

                if not bom_color:
                    frappe.throw(f"Color for BOM {bom} not found in Custom BOM {self.custom_bom}")

                accumulated_qty = 0
                selected = []

                other_batches = frappe.get_all(
                    "Parts Batch",
                    filters={
                        "source_bom": bom,
                        "color": bom_color,
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
                            "qty": take_qty,
                            "finish_good_index": main_batch.finish_good_index
                        })

                if accumulated_qty < required_qty:
                    frappe.throw(
                        f"Not enough parts for BOM <b>{bom}</b> with color <b>{bom_color}</b> and size <b>{size}</b> "
                        f"(Needed: {required_qty}, Found: {accumulated_qty}) for main batch <b>{main_batch_name}</b>"
                    )

        self.set("finish_goods", [])
        template = c_bom.special_item

        variants = frappe.get_all(
            "Item",
            filters={
                "variant_of": template,
                "disabled": 0
            },
            fields=["name", "item_code"]
        )

        for idx, batch in enumerate(self.main_batches):
            size = batch.size.strip().lower()
            matched_variant = None

            for v in variants:
                attributes = frappe.get_all(
                    "Item Variant Attribute",
                    filters={"parent": v.name},
                    fields=["attribute", "attribute_value"]
                )

                has_size = any(attr.attribute == "Size" and attr.attribute_value.strip().lower() == size for attr in attributes)

                if has_size:
                    matched_variant = v.item_code
                    break

            if matched_variant:
                barcode = generate_barcode(self.name, idx)
                self.append("finish_goods", {
                    "item": matched_variant,
                    "qty": batch.parts_qty,
                    "barcode": barcode,
                    "idx": idx
                })
            else:
                frappe.throw(f"No variant found for size <b>{batch.size}</b>.")

        parts_cost = 0.0

        # MAIN BATCH COSTS
        for batch in self.main_batches:
            batch_doc = frappe.get_doc("Parts Batch", batch.batch)
            pgcd = reduce(math.gcd, [int(p.qty) for p in batch_doc.parts if p.qty and float(p.qty).is_integer()])
            if not pgcd:
                continue

            total_batch_cost = 0.0
            for p in batch_doc.parts:
                if not p.qty or not p.cost_per_one:
                    continue

                unit_ratio = p.qty / pgcd
                used_qty = unit_ratio * batch.parts_qty
                cost = used_qty * p.cost_per_one
                total_batch_cost += cost

            batch.cost = total_batch_cost
            parts_cost += total_batch_cost

        for batch in self.other_batches:
            batch_doc = frappe.get_doc("Parts Batch", batch.batch)
            pgcd = reduce(math.gcd, [int(p.qty) for p in batch_doc.parts if p.qty and float(p.qty).is_integer()])
            if not pgcd:
                continue

            total_batch_cost = 0.0
            for p in batch_doc.parts:
                if not p.qty or not p.cost_per_one:
                    continue

                unit_ratio = p.qty / pgcd
                used_qty = unit_ratio * batch.qty
                cost = used_qty * p.cost_per_one
                total_batch_cost += cost

            batch.cost = total_batch_cost
            parts_cost += total_batch_cost
        
        for idx, fg in enumerate(self.finish_goods):
            cost = 0.0

            for mb in self.main_batches:
                if mb.finish_good_index == idx:
                    cost += mb.cost or 0.0

            for ob in self.other_batches:
                if ob.finish_good_index == idx:
                    cost += ob.cost or 0.0

            fg.cost = cost
            fg.cost_per_one = cost / fg.qty if fg.qty else 0
            total_qty = sum(fgg.qty for fgg in self.finish_goods if fgg.qty)
            fg.cost_per_one_adding_assemblying = fg.cost_per_one + (self.total_cost_without_parts / total_qty if total_qty else 0)
            fg.total_finish_good_adding_assemblying = fg.cost_per_one_adding_assemblying * fg.qty
        
        for p in self.finish_goods:
            if not p.item:
                continue

        self.parts_cost = parts_cost
        self.total_cost = total_cost + individual_cost + parts_cost


    def on_submit(self):
        if not self.finish_goods or not self.other_batches or not self.main_batches:
            frappe.throw("No finish goods found.")

        company = frappe.defaults.get_user_default("Company")

        issue = frappe.new_doc("Stock Entry")
        issue.purpose = issue.stock_entry_type = "Material Transfer"
        issue.company = company

        def add_item(item_code, qty, from_warehouse, to_warehouse, rate):
            uom = frappe.db.get_value("Item", item_code, "stock_uom")
            issue.append("items", {
                "item_code": item_code,
                "qty": qty,
                "uom": uom,
                "stock_uom": uom,
                "conversion_factor": 1,
                "allow_zero_valuation_rate": 1,
                "valuation_rate": rate,
                "set_basic_rate_manually": 1,
                "basic_rate": rate,
                "s_warehouse": from_warehouse,
                "t_warehouse": to_warehouse
            })

        def process_batches(batches, is_main):
            consumptions = []
            for b in batches:
                pb = frappe.get_doc("Parts Batch", b.batch)
                source_wh = frappe.get_doc("cutting operation", pb.source_operation).distination_warehouse
                dest_wh = self.distination_warehouse

                qtys = [p.qty for p in pb.parts if p.qty and p.qty > 0]
                ints = [int(q) for q in qtys if float(q).is_integer()]
                pgcd = reduce(math.gcd, ints) if ints else 1

                if pgcd <= 0:
                    continue

                multiplier = b.parts_qty if is_main else b.qty

                for p in pb.parts:
                    if p.qty:
                        to_consume = (p.qty / pgcd) * multiplier
                        consumptions.append((b.batch, p.part, to_consume, source_wh, dest_wh, p.cost_per_one, p.name))
            return consumptions

        main_consumption = process_batches(self.main_batches, True)
        other_consumption = process_batches(self.other_batches, False)

        def reserve_and_update(consumption_list):
            for batch_name, part_code, qty_used, _, _, _, part_rowname in consumption_list:
                pb = frappe.get_doc("Parts Batch", batch_name)
                for row in pb.parts:
                    if row.part == part_code:
                        old_qty = row.qty or 0
                        old_reserved = row.reserved_qty or 0
                        available_qty = old_qty - old_reserved

                        if available_qty < qty_used:
                            continue

                        frappe.db.set_value("Parts", row.name, {
                            "qty": old_qty - qty_used,
                            "reserved_qty": old_reserved + qty_used
                        })
                        break

        reserve_and_update(main_consumption)
        reserve_and_update(other_consumption)

        for batch_name, part_code, qty_used, source_wh, dest_wh, cost, _ in main_consumption + other_consumption:
            add_item(part_code, qty_used, source_wh, dest_wh, cost)

        if not issue.items:
            frappe.throw("No items were added to the Stock Entry.")

        issue.insert()
        issue.submit()
        self.db_set("stock_entry_name", issue.name)

    def on_cancel(self):
        if self.stock_entry_name:
            try:
                se = frappe.get_doc("Stock Entry", self.stock_entry_name)
                if se.docstatus == 1:
                    se.cancel()
            except Exception as e:
                frappe.throw(f"Could not cancel Stock Entry {self.stock_entry_name}: {e}")

        def restore_parts(batches, is_main):
            for b in batches:
                pb = frappe.get_doc("Parts Batch", b.batch)

                qtys = [p.qty for p in pb.parts if p.qty and p.qty > 0]
                ints = [int(q) for q in qtys if float(q).is_integer()]
                pgcd = reduce(math.gcd, ints) if ints else 1
                if pgcd <= 0:
                    continue

                multiplier = b.parts_qty if is_main else b.qty

                for row in pb.parts:
                    if not row.qty and not row.reserved_qty:
                        continue

                    to_restore = (row.qty + row.reserved_qty) / pgcd * multiplier if pgcd else 0

                    old_qty = row.qty or 0
                    old_reserved = row.reserved_qty or 0

                    new_qty = old_qty + to_restore
                    new_reserved = max(old_reserved - to_restore, 0)

                    frappe.db.set_value("Parts", row.name, {
                        "qty": new_qty,
                        "reserved_qty": new_reserved
                    })

        restore_parts(self.main_batches, True)
        restore_parts(self.other_batches, False)

        self.db_set("stock_entry_name", None)

