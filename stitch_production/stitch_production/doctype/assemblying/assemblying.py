import frappe
from frappe.model.document import Document
import math
from functools import reduce
from decimal import Decimal, ROUND_HALF_UP
import json
import random


def generate_barcode(index):
    random_part = ''.join([str(random.randint(0, 9)) for _ in range(8)])
    index_part = str(index).zfill(2)
    return f"{random_part}{index_part}"

def generate_barcode_assembly():
    return ''.join([str(random.randint(0, 9)) for _ in range(12)])
    


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
        for idx, pb in enumerate(batch_names, start=1):
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
        batch_number_check_counter = 1

        # Other batches
        batch_number_check_counter = 1 

        for main_batch in self.main_batches:
            color = main_batch.color
            size = main_batch.size
            required_qty = main_batch.parts_qty
            main_batch_name = main_batch.batch

            for bom in other_boms:
                accumulated_qty = 0
                current_group_batches = []

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

                        # Append to current group, to apply batch_number_check together later
                        current_group_batches.append({
                            "batch": ob.batch_name,
                            "qty": take_qty,
                            "finish_good_index": main_batch.finish_good_index,
                            "batch_number_check": float(batch_number_check_counter)
                        })

                if current_group_batches:
                    for b in current_group_batches:
                        self.append("other_batches", b)
                    batch_number_check_counter += 1  # Increment only if group used

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

        fg_idx = 1
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

        for idx, pb in enumerate(batch_names, start=1):
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
        batch_number_check_counter = 1

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
                current_group_batches = []

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

                        current_group_batches.append({
                            "batch": ob.batch_name,
                            "qty": take_qty,
                            "finish_good_index": main_batch.finish_good_index,
                            "batch_number_check": float(batch_number_check_counter)
                        })

                if current_group_batches:
                    for b in current_group_batches:
                        self.append("other_batches", b)
                    batch_number_check_counter += 1  # increment only if used

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

        for idx, batch in enumerate(self.main_batches, start=1):
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

        for idx, fg in enumerate(self.finish_goods, start=1):
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


    def before_submit(self):
        self.barcode = generate_barcode_assembly()
        if not self.barcode:
            frappe.throw("Could not generate barcode for assembly.")

        updated_batches = set()
        damage_map = {}

        # === Handle MAIN BATCHES ===
        for mb in self.main_batches:
            fg = next((f for f in self.finish_goods if f.finish_good_index == mb.finish_good_index), None)
            if not fg:
                continue

            prev_qty = mb.original_parts_qty or mb.parts_qty or 0
            new_qty = fg.real_qty
            lost_qty = max(prev_qty - new_qty, 0)

            mb.parts_qty = new_qty

            if lost_qty > 0:
                pb = frappe.get_doc("Parts Batch", mb.batch)

                for part_row in pb.parts:
                    if part_row.qty_of_finished_goods and part_row.qty:
                        reduction = lost_qty * part_row.qty_of_finished_goods
                        part_row.qty = max((part_row.qty or 0) - reduction, 0)

                        existing = next((row for row in pb.qty_perts
                                        if row.operation == self.name and row.item == part_row.part), None)
                        if existing:
                            existing.perts_qty += reduction
                        else:
                            pb.append("qty_perts", {
                                "operation": self.name,
                                "item": part_row.part,
                                "perts_qty": reduction,
                                "cost_per_one": part_row.cost_per_one
                            })

                        damage_map.setdefault(pb.name, []).append((part_row.part, reduction, part_row.batch_number or "", part_row.cost_per_one or 0))

                pb.save(ignore_permissions=True)
                updated_batches.add(pb.name)

        for ob in self.other_batches:
            fg = next((f for f in self.finish_goods if f.finish_good_index == ob.finish_good_index), None)
            if not fg:
                continue

            prev_qty = ob.original_parts_qty or ob.qty or 0
            new_qty = ob.new_qty_pivot or 0
            lost_qty = max(prev_qty - new_qty, 0)

            if lost_qty > 0:
                pb = frappe.get_doc("Parts Batch", ob.batch)

                for part_row in pb.parts:
                    if part_row.qty_of_finished_goods and part_row.qty:
                        reduction = lost_qty * part_row.qty_of_finished_goods
                        part_row.qty = max((part_row.qty or 0) - reduction, 0)

                        existing = next((row for row in pb.qty_perts
                                        if row.operation == self.name and row.item == part_row.part), None)
                        if existing:
                            existing.perts_qty += reduction
                        else:
                            pb.append("qty_perts", {
                                "operation": self.name,
                                "item": part_row.part,
                                "perts_qty": reduction,
                                "cost_per_one": part_row.cost_per_one
                            })

                        damage_map.setdefault(pb.name, []).append((part_row.part, reduction, part_row.batch_number or "", part_row.cost_per_one or 0))

                pb.save(ignore_permissions=True)
                updated_batches.add(pb.name)
        for pb_name in updated_batches:
            frappe.get_doc("Parts Batch", pb_name).save(ignore_permissions=True)

        self.db_set("_damage_map_json", json.dumps(damage_map))





    def on_submit(self):
        if not self.finish_goods or not self.other_batches or not self.main_batches:
            frappe.throw("No finish goods found.")

        company = frappe.defaults.get_user_default("Company")

        consumed_map = {}
        workers_account = self.workers_account
        extra_cost_account = self.assembly_extra_cost_account
        damage_cost_account = self.assembly_damage_account

        transfer_entry = frappe.new_doc("Stock Entry")
        transfer_entry.purpose = transfer_entry.stock_entry_type = "Material Transfer"
        transfer_entry.company = company

        def add_transfer_item(item_code, qty, s_warehouse, t_warehouse, rate, batch_no):
            uom = frappe.db.get_value("Item", item_code, "stock_uom")
            transfer_entry.append("items", {
                "item_code": item_code,
                "qty": float(qty),
                "uom": uom,
                "stock_uom": uom,
                "conversion_factor": 1,
                "s_warehouse": s_warehouse,
                "t_warehouse": t_warehouse,
                "use_serial_batch_fields": 1,
                "batch_no": batch_no,
                "basic_rate": rate or 0
            })

        def process_batches(batches, is_main):
            result = []
            for b in batches:
                pb = frappe.get_doc("Parts Batch", b.batch)
                source_wh = frappe.get_doc("cutting operation", pb.source_operation).distination_warehouse
                dest_wh = self.distination_warehouse
                finish_qty = b.parts_qty if is_main else b.qty

                for p in pb.parts:
                    if not p.qty or not p.qty_of_finished_goods:
                        frappe.throw(f"Invalid qty or ratio for part {p.part} in batch {b.batch}")
                    to_consume = finish_qty * p.qty_of_finished_goods
                    result.append((b.batch, p.part, to_consume, source_wh, dest_wh, p.cost_per_one or 0, p.name, p.batch_number or ""))
            return result

        main_consumption = process_batches(self.main_batches, True)
        other_consumption = process_batches(self.other_batches, False)
        all_consumption = main_consumption + other_consumption

        for batch_name, part_code, qty_used, _, _, _, part_rowname, batch_number in all_consumption:
            pb = frappe.get_doc("Parts Batch", batch_name)
            for row in pb.parts:
                if row.part == part_code:
                    row.qty = max((row.qty or 0) - qty_used, 0)
                    existing = next((r for r in pb.batches_reserves if r.part == row.part and r.operation == self.name), None)
                    if existing:
                        existing.reserved_qty += qty_used
                    else:
                        pb.append("batches_reserves", {
                            "part": row.part,
                            "operation": self.name,
                            "reserved_qty": qty_used
                        })
                    pb.save(ignore_permissions=True)
                    consumed_map[row.name] = float(qty_used)
                    break

        self.db_set("_consumed_qty_map_json", json.dumps(consumed_map))

        for batch_name, part_code, qty_used, source_wh, dest_wh, cost, _, batch_number in all_consumption:
            add_transfer_item(part_code, qty_used, source_wh, dest_wh, cost, batch_number)

        damage_map = json.loads(self._damage_map_json or "{}")
        if damage_map:
            damage_issue = frappe.new_doc("Stock Entry")
            damage_issue.purpose = damage_issue.stock_entry_type = "Material Issue"
            damage_issue.company = company

            for batch_name, parts in damage_map.items():
                pb = frappe.get_doc("Parts Batch", batch_name)
                source_wh = frappe.get_doc("cutting operation", pb.source_operation).distination_warehouse

                for part_code, lost_qty, batch_number, cost_per_one in parts:
                    uom = frappe.db.get_value("Item", part_code, "stock_uom")
                    damage_issue.append("items", {
                        "item_code": part_code,
                        "qty": float(lost_qty),
                        "uom": uom,
                        "stock_uom": uom,
                        "conversion_factor": 1,
                        "s_warehouse": source_wh,
                        "batch_no": batch_number,
                        "use_serial_batch_fields": 1,
                    })

            damage_issue.insert()
            self.db_set("damage_issue_name", damage_issue.name)
            damage_issue.submit()

            damage_receipt = frappe.new_doc("Stock Entry")
            damage_receipt.purpose = damage_receipt.stock_entry_type = "Material Receipt"
            damage_receipt.company = company

            for batch_name, parts in damage_map.items():
                for part_code, lost_qty, batch_number, cost_per_one in parts:
                    uom = frappe.db.get_value("Item", part_code, "stock_uom")
                    damage_receipt.append("items", {
                        "item_code": part_code,
                        "qty": float(lost_qty),
                        "uom": uom,
                        "stock_uom": uom,
                        "conversion_factor": 1,
                        "t_warehouse": self.damage_parts_warehouse,
                        "batch_no": batch_number,
                        "basic_rate": 0
                    })

            if damage_receipt.items:
                damage_receipt.insert()
                damage_receipt.submit()
            self.db_set("damage_receipt_name", damage_receipt.name)
        total_extra = self.individual_cost or 0
        total_workers = self.workers_total_cost or 0
        # total_damage_cost = sum(
        #     float(p[1]) * float(p[3])
        #     for parts in damage_map.values() for p in parts
        # )
        #calcule total_damage_cost  
        total_damage_cost = 0
        for batch_name, parts in damage_map.items():
            for part_code, lost_qty, batch_number, cost_per_one in parts:
                total_damage_cost += lost_qty * cost_per_one
                frappe.msgprint(f"Batch: {batch_name}, Part: {part_code}, Lost Qty: {lost_qty}, Cost Per One: {cost_per_one}")
        frappe.msgprint(f"Total Damage Cost: {total_damage_cost}")
        

        if transfer_entry.items:
            if total_workers:
                transfer_entry.append("additional_costs", {
                    "expense_account": workers_account,
                    "description": "Workers cost",
                    "amount": total_workers
                })
            if total_extra:
                transfer_entry.append("additional_costs", {
                    "expense_account": extra_cost_account,
                    "description": "Extra cost",
                    "amount": total_extra
                })
            if total_damage_cost:
                transfer_entry.append("additional_costs", {
                    "expense_account": damage_cost_account,
                    "description": "Damaged parts cost",
                    "amount": total_damage_cost
                })
            transfer_entry.insert()
            transfer_entry.submit()
            self.db_set("stock_entry_name", transfer_entry.name)

        for b in self.main_batches + self.other_batches:
            pb = frappe.get_doc("Parts Batch", b.batch)
            qtys = [p.qty for p in pb.parts if p.qty and p.qty > 0]
            ints = [int(q) for q in qtys if float(q).is_integer()]
            pgcd = reduce(math.gcd, ints) if ints else 0
            frappe.db.set_value("Parts Batch", pb.name, "pgcd_qty", pgcd)

        for fg in self.finish_goods:
            if not (fg.barcode and fg.item and fg.qty and fg.color and fg.size and fg.cost_per_one_adding_assemblying and fg.total_finish_good_adding_assemblying):
                continue
            ps = frappe.new_doc("Post Assembly")
            ps.status = "Assembly"
            ps.finished = fg.item
            ps.qty = fg.qty
            ps.cost_per_one = fg.total_finish_good_adding_assemblying / fg.qty
            ps.operation = self.name
            ps.total_cost = fg.total_finish_good_adding_assemblying
            ps.color = fg.color
            ps.size = fg.size
            ps.barcode = fg.barcode
            ps.insert()

            # frappe.msgprint("cost per one adding assembly before ",fg.cost_per_one_adding_assemblying)
            # fg.cost_per_one_adding_assemblying = fg.total_finish_good_adding_assemblying / fg.qty
            # frappe.msgprint("cost per one adding assembly after ",fg.cost_per_one_adding_assemblying)
            # self.set("finish_goods", self.finish_goods)
            # self.save(ignore_permissions=True)


    def before_cancel(self):
        frappe.flags.ignore_linked_with = True

        self._batch_data_for_rollback = []

        for b in self.main_batches + self.other_batches:
            if not b.batch:
                continue
            pb = frappe.get_doc("Parts Batch", b.batch)
            batch_info = {
                "name": pb.name,
                "reserved_qty": {r.part: r.reserved_qty for r in pb.batches_reserves if r.operation == self.name},
                "damage_qty": {r.item: r.perts_qty for r in pb.qty_perts if r.operation == self.name}
            }
            self._batch_data_for_rollback.append(batch_info)

        for row in self.main_batches:
            row.batch = None
        for row in self.other_batches:
            row.batch = None


    def on_cancel(self):
        frappe.flags.ignore_linked_with = True
        self.ignore_linked_doctypes = ("Parts Batch",)

        try:
            for field in ("stock_entry_name", "damage_issue_name", "damage_receipt_name"):
                name = self.get(field)
                if name:
                    try:
                        self.db_set(field, None)
                        se = frappe.get_doc("Stock Entry", name)
                        if se.docstatus == 1:
                            se.cancel()
                            se.delete()
                    except frappe.DoesNotExistError:
                        pass
                    except Exception as e:
                        frappe.log_error(f"Failed to cancel Stock Entry {name}: {e}")

            for batch_data in getattr(self, "_batch_data_for_rollback", []):
                try:
                    pb = frappe.get_doc("Parts Batch", batch_data["name"])
                    for part_code, qty in batch_data["reserved_qty"].items():
                        for row in pb.parts:
                            if row.part == part_code:
                                row.qty = (row.qty or 0) + qty
                        pb.batches_reserves = [r for r in pb.batches_reserves if not (r.part == part_code and r.operation == self.name)]

                    for item_code, qty in batch_data["damage_qty"].items():
                        for row in pb.parts:
                            if row.part == item_code:
                                row.qty = (row.qty or 0) + qty
                        pb.qty_perts = [r for r in pb.qty_perts if not (r.item == item_code and r.operation == self.name)]

                    qtys = [p.qty for p in pb.parts if p.qty and p.qty > 0]
                    ints = [int(q) for q in qtys if float(q).is_integer()]
                    pgcd = reduce(math.gcd, ints) if ints else 0
                    pb.pgcd_qty = pgcd

                    pb.save(ignore_permissions=True)

                except Exception as e:
                    frappe.log_error(f"Failed to rollback Parts Batch {batch_data['name']}: {e}")

            pa_list = frappe.get_all("Post Assembly", filters={"operation": self.name})
            for p in pa_list:
                pa_doc = frappe.get_doc("Post Assembly", p.name)
                if pa_doc.docstatus == 1:
                    name = pa_doc.stock_enry_receipt
                    try:
                        pa_doc.db_set("stock_enry_receipt", None)
                        se = frappe.get_doc("Stock Entry", name)
                        if se.docstatus == 1:
                            se.cancel()
                            se.delete()
                    except frappe.DoesNotExistError:
                        pass
                    except Exception as e:
                        frappe.log_error(f"Failed to cancel Stock Entry {name}: {e}")

                    pa_doc.cancel()
                    pa_doc.delete()
                else:
                    pa_doc.delete()

        finally:
            frappe.flags.ignore_linked_with = False
