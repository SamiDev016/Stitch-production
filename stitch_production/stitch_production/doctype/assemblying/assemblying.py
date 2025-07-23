import frappe
from frappe.model.document import Document
import math
from functools import reduce
from decimal import Decimal, ROUND_HALF_UP
import json
import random


# def generate_barcode(name, index):
#     return f"{name}-{str(index).zfill(2)}"





def generate_barcode(index):
    random_part = ''.join([str(random.randint(0, 9)) for _ in range(8)])
    index_part = str(index).zfill(2)
    return f"{random_part}{index_part}"


class Assemblying(Document):
    def before_save(self):
        if not self.special_assembly:
            self.handle_normal_assembly()
        else:
            self.handle_special_assembly()

    def handle_normal_assembly(self):
        batch_names = frappe.get_all(
            "Parts Batch",
            filters={"source_operation": self.main_operation, "source_bom": self.main_bom},
            fields=["name", "batch_name", "color", "size"]
        )

        if not batch_names:
            frappe.throw("No Parts Batch found for those criteria.")

        self.set("main_batches", [])
        self.set("other_batches", [])

        # Main batches
        for idx, pb in enumerate(batch_names):
            batch_doc = frappe.get_doc("Parts Batch", pb["name"])
            possible_quantities = []
            for part in batch_doc.parts:
                if not part.qty or not part.qty_of_finished_goods:
                    continue
                if part.qty_of_finished_goods <= 0:
                    frappe.throw(f"Invalid qty_of_finished_goods for part {part.part} in batch {pb['batch_name']}")
                qty_possible = part.qty / part.qty_of_finished_goods
                possible_quantities.append(qty_possible)

            if not possible_quantities:
                frappe.throw(f"No valid parts with qty and qty_of_finished_goods found in batch {pb['batch_name']}")

            min_qty = math.floor(min(possible_quantities))

            self.append("main_batches", {
                "batch": pb["batch_name"],
                "color": pb["color"],
                "size": pb["size"],
                "parts_qty": min_qty,
                "finish_good_index": idx
            })

        if not self.parent_bom:
            frappe.throw("Parent BOM not set")

        p_doc = frappe.get_doc("Parent BOM", self.parent_bom)
        other_boms = [b.bom for b in p_doc.boms if b.bom != self.main_bom]
        

        # Other batches
        for main_batch in self.main_batches:
            color = main_batch.color
            size = main_batch.size
            required_qty = main_batch.parts_qty
            main_batch_name = main_batch.batch

            for bom in other_boms:
                accumulated_qty = 0

                other_batches = frappe.get_all(
                    "Parts Batch",
                    filters={"source_bom": bom, "color": color, "size": size},
                    fields=["name", "batch_name"]
                )

                for ob in other_batches:
                    if accumulated_qty >= required_qty:
                        break

                    ob_doc = frappe.get_doc("Parts Batch", ob.name)

                    possible_quantities = []
                    for part in ob_doc.parts:
                        if not part.qty or not part.qty_of_finished_goods:
                            continue
                        if part.qty_of_finished_goods <= 0:
                            frappe.throw(f"Invalid qty_of_finished_goods for part {part.part} in batch {ob['batch_name']}")
                        qty_possible = part.qty / part.qty_of_finished_goods
                        possible_quantities.append(qty_possible)

                    min_qty = math.floor(min(possible_quantities)) if possible_quantities else 0

                    if min_qty > 0:
                        take_qty = min(min_qty, required_qty - accumulated_qty)
                        accumulated_qty += take_qty

                        self.append("other_batches", {
                            "batch": ob.batch_name,
                            "qty": take_qty,
                            "finish_good_index": main_batch.finish_good_index
                        })

                if accumulated_qty < required_qty:
                    frappe.throw(
                        f"Not enough parts for BOM <b>{bom}</b> with color <b>{color}</b> and size <b>{size}</b>. "
                        f"Needed: {required_qty}, Found: {accumulated_qty} for main batch <b>{main_batch_name}</b>"
                    )

        # Finish Goods
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
                barcode = generate_barcode(fg_idx)
                self.append("finish_goods", {
                    "item": matched_variant,
                    "qty": batch.parts_qty,
                    "barcode": barcode,
                    "color": color,
                    "size": size,
                    "finish_good_index": fg_idx
                })
            else:
                frappe.throw(f"No variant found for color <b>{batch.color}</b> and size <b>{batch.size}</b>.")
            fg_idx += 1

        # Cost Calculation
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
            total_batch_cost = 0.0
            multiplier = batch.parts_qty if hasattr(batch, 'parts_qty') else batch.qty

            for p in batch_doc.parts:
                if not p.qty or not p.cost_per_one or not p.qty_of_finished_goods:
                    continue
                used_qty = p.qty_of_finished_goods * multiplier
                cost = used_qty * p.cost_per_one
                total_batch_cost += cost

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
            workers_total_cost += w.employee_cost
            total_cost += w.employee_cost
            total_cost_without_parts += w.employee_cost

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
            possible_quantities = []
            for part in batch_doc.parts:
                if not part.qty or not part.qty_of_finished_goods:
                    continue
                if part.qty_of_finished_goods <= 0:
                    frappe.throw(f"Invalid qty_of_finished_goods for part {part.part} in batch {pb['batch_name']}")
                qty_possible = part.qty / part.qty_of_finished_goods
                possible_quantities.append(qty_possible)

            if not possible_quantities:
                frappe.throw(f"No valid parts with qty and qty_of_finished_goods found in batch {pb['batch_name']}")

            min_qty = math.floor(min(possible_quantities))

            self.append("main_batches", {
                "batch": pb["batch_name"],
                "color": pb["color"],
                "size": pb["size"],
                "parts_qty": min_qty,
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
                    possible_quantities = []
                    for part in ob_doc.parts:
                        if not part.qty or not part.qty_of_finished_goods:
                            continue
                        if part.qty_of_finished_goods <= 0:
                            frappe.throw(f"Invalid qty_of_finished_goods for part {part.part} in batch {ob['batch_name']}")
                        qty_possible = part.qty / part.qty_of_finished_goods
                        possible_quantities.append(qty_possible)

                    min_qty = math.floor(min(possible_quantities)) if possible_quantities else 0

                    if min_qty > 0:
                        take_qty = min(min_qty, required_qty - accumulated_qty)
                        accumulated_qty += take_qty

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
            filters={"variant_of": template, "disabled": 0},
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
                barcode = generate_barcode(idx)
                self.append("finish_goods", {
                    "item": matched_variant,
                    "qty": batch.parts_qty,
                    "barcode": barcode,
                    "size": batch.size,
                    "finish_good_index": idx
                })
            else:
                frappe.throw(f"No variant found for size <b>{batch.size}</b>.")

        parts_cost = 0.0

        for batch in self.main_batches + self.other_batches:
            batch_doc = frappe.get_doc("Parts Batch", batch.batch)
            total_batch_cost = 0.0
            multiplier = batch.parts_qty if hasattr(batch, 'parts_qty') else batch.qty

            for p in batch_doc.parts:
                if not p.qty or not p.cost_per_one or not p.qty_of_finished_goods:
                    continue
                used_qty = p.qty_of_finished_goods * multiplier
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

        self.parts_cost = parts_cost
        self.total_cost = total_cost + individual_cost + parts_cost

    def on_submit(self):
        if not self.finish_goods or not self.other_batches or not self.main_batches:
            frappe.throw("No finish goods found.")

        company = frappe.defaults.get_user_default("Company")

        issue = frappe.new_doc("Stock Entry")
        issue.purpose = issue.stock_entry_type = "Material Transfer"
        issue.company = company

        consumed_map = {}

        def add_item(item_code, qty, from_warehouse, to_warehouse, rate,batch_number):
            uom = frappe.db.get_value("Item", item_code, "stock_uom")
            issue.append("items", {
                "item_code": item_code,
                "qty": float(qty),
                "uom": uom,
                "stock_uom": uom,
                "conversion_factor": 1,
                # "valuation_rate": float(rate),
                # "basic_rate": float(rate),
                # "set_basic_rate_manually": 1,
                # "allow_zero_valuation_rate": 1,
                "s_warehouse": from_warehouse,
                "t_warehouse": to_warehouse,
                "use_serial_batch_fields": 1,
                "batch_no": batch_number
            })

        def process_batches(batches, is_main):
            consumptions = []
            for b in batches:
                pb = frappe.get_doc("Parts Batch", b.batch)
                source_wh = frappe.get_doc("cutting operation", pb.source_operation).distination_warehouse
                dest_wh = self.distination_warehouse

                finish_qty = b.parts_qty if is_main else b.qty

                for p in pb.parts:
                    if not p.qty or not p.qty_of_finished_goods:
                        frappe.throw(f"Invalid 'qty' or 'qty_of_finished_goods' for part {p.part} in batch {b.batch}")
                    part_key = p.name
                    base_qty = p.qty
                    fg_qty = p.qty_of_finished_goods

                    if fg_qty <= 0:
                        frappe.throw(f"Invalid 'qty_of_finished_goods' for part {p.part} in batch {b.batch}")

                    to_consume = finish_qty * fg_qty

                    cost = p.cost_per_one or 0
                    batch_number = p.batch_number or ""
                    consumptions.append((b.batch, p.part, to_consume, source_wh, dest_wh, cost, part_key,batch_number))
            return consumptions




        main_consumption = process_batches(self.main_batches, True)
        other_consumption = process_batches(self.other_batches, False)
        all_consumption = main_consumption + other_consumption
        
        for batch_name, part_code, qty_used, _, _, _, part_rowname,batch_number in all_consumption:
            pb = frappe.get_doc("Parts Batch", batch_name)
            for row in pb.parts:
                if row.part == part_code:
                    old_qty = row.qty or 0
                    new_qty = old_qty - qty_used

                    row.qty = float(new_qty)


                    already_reserved = False
                    for reserve in pb.batches_reserves:
                        if reserve.part == row.part and reserve.operation == self.name:
                            reserve.reserved_qty += qty_used
                            already_reserved = True
                            break

                    if not already_reserved:
                        pb.append("batches_reserves", {
                            "part": row.part,
                            "operation": self.name,
                            "reserved_qty": qty_used
                        })

                    pb.save(ignore_permissions=True)
                    consumed_map[row.name] = float(qty_used)
                    break

        self.db_set("_consumed_qty_map_json", json.dumps(consumed_map))

        for batch_name, part_code, qty_used, source_wh, dest_wh, cost, part_rowname,batch_number in all_consumption:
            add_item(part_code, qty_used, source_wh, dest_wh, cost, batch_number)

        if not issue.items:
            frappe.throw("No items were added to the Stock Entry.")

        issue.insert()
        issue.submit()
        self.db_set("stock_entry_name", issue.name)

        for b in self.main_batches + self.other_batches:
            pb = frappe.get_doc("Parts Batch", b.batch)
            qtys = [p.qty for p in pb.parts if p.qty and p.qty > 0]
            ints = [int(q) for q in qtys if float(q).is_integer()]
            pgcd = reduce(math.gcd, ints) if ints else 0
            frappe.db.set_value("Parts Batch", pb.name, "pgcd_qty", pgcd)


@frappe.whitelist()
def force_cancel(docname):
    doc = frappe.get_doc("Assemblying", docname)
    try:
        consumed_map = json.loads(doc._consumed_qty_map_json or "{}")
    except Exception:
        consumed_map = {}

    def unlink_parts_batch_operations(batches):
        for b in batches:
            pb = frappe.get_doc("Parts Batch", b.batch)

            for r in pb.batches_reserves:
                if r.operation == doc.name:
                    frappe.db.set_value("Batches Reserves", r.name, "operation", None)

            frappe.db.commit()
            pb.reload()

            pb.batches_reserves = [r for r in pb.batches_reserves if r.operation]
            
            for row in pb.parts:
                used_qty = Decimal(str(consumed_map.get(row.name, 0)))
                if used_qty:
                    row.qty = (Decimal(str(row.qty or 0)) + used_qty).quantize(Decimal("0.00001"))

            qtys = [p.qty for p in pb.parts if p.qty and p.qty > 0]
            ints = [int(q) for q in qtys if float(q).is_integer()]
            pb.pgcd_qty = reduce(math.gcd, ints) if ints else 0

            pb.save(ignore_permissions=True)

    unlink_parts_batch_operations(doc.main_batches)
    unlink_parts_batch_operations(doc.other_batches)

    if doc.stock_entry_name:
        try:
            se = frappe.get_doc("Stock Entry", doc.stock_entry_name)
            if se.docstatus == 1:
                se.flags.ignore_linked_doctypes = ('Assemblying',)
                se.cancel()
        except Exception as e:
            frappe.log_error(f"Failed to cancel Stock Entry {doc.stock_entry_name}: {e}")

    doc.db_set("stock_entry_name", None)
    doc.db_set("_consumed_qty_map_json", None)

    frappe.db.commit()
    doc.cancel()

    frappe.msgprint("Force cancel complete, quantities restored.")
