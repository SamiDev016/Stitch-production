function setup_main_bom_query(frm) {
    frm.set_df_property("main_bom", "hidden", 1);

    if (frm.doc.main_operation) {
        frappe.call({
            method: "frappe.client.get",
            args: {
                doctype: "cutting operation",
                name: frm.doc.main_operation
            },
            callback: function (r) {
                if (!r.message) return;

                let bom_list = (r.message.parent_boms || []).map(row => row.parent_bom);

                if (bom_list.length) {
                    frm.set_df_property("main_bom", "hidden", 0);

                    frm.set_query("main_bom", function () {
                        return {
                            filters: [["name", "in", bom_list]]
                        };
                    });
                } else {
                    frappe.msgprint("No BOMs linked to the selected Main Operation.");
                }
            }
        });
    }
}

function setup_parent_bom_query(frm) {
    frm.set_df_property("parent_bom", "hidden", 1);
    if (!frm.special_assembly)
    {
    
    if (frm.doc.main_bom) {
        frappe.call({
            method: "stitch_production.api.get_parent_boms_containing_main_bom",
            args: {
                main_bom: frm.doc.main_bom
            },
            callback: function (r) {
                if (!r.message || r.message.length === 0) {
                    frappe.msgprint("No Parent BOMs found containing the selected Main BOM.");
                    return;
                }

                frm.set_df_property("parent_bom", "hidden", 0);

                frm.set_query("parent_bom", function () {
                    return {
                        filters: [["name", "in", r.message]]
                    };
                });
            }
        });
    }
}else{
    frm.set_value("parent_bom", null);
    frm.set_df_property("parent_bom", "hidden", 0);
}

}



frappe.ui.form.on("Assemblying", {
    onload_post_render(frm) {
        setup_main_bom_query(frm);
    },

    main_operation(frm) {
        frm.set_value("main_bom", null);
        frm.set_value("parent_bom", null);
        setup_main_bom_query(frm);
    },

    main_bom(frm) {
        frm.set_value("parent_bom", null);
        setup_parent_bom_query(frm);
    },

    refresh(frm) {
        if (frm.doc.docstatus === 1) {
            frm.add_custom_button("Force Cancel", () => {
                frappe.confirm(
                    "Are you sure you want to force cancel and unlink all references?",
                    () => {
                        frappe.call({
                            method: "stitch_production.stitch_production.doctype.assemblying.assemblying.force_cancel",
                            args: {
                                docname: frm.doc.name
                            },
                            callback: function (r) {
                                if (!r.exc) {
                                    frappe.show_alert("Force canceled successfully!");
                                    frm.reload_doc();
                                }
                            }
                        });
                    }
                );
            });
        }

        if (frm.doc.docstatus === 0 && frm.doc.finish_goods && frm.doc.finish_goods.length) {
            frm.add_custom_button(__('Handle Damage'), () => {
                show_damage_dialog(frm);
            });
        }
    },

    before_submit(frm) {
        let fg = frm.doc.finish_goods || [];
        let needs_review = fg.some(row => !row.real_qty || row.real_qty !== row.qty);

        if (needs_review) {
            frappe.throw(__('Please confirm Real Quantities using "Handle Damage" before submitting.'));
        }
    }
});

function show_damage_dialog(frm) {
    const fields = frm.doc.finish_goods.map((fg, idx) => ({
        fieldtype: 'Float',
        label: `${fg.item} (Planned: ${fg.qty})`,
        fieldname: `real_qty_${idx}`,
        default: fg.real_qty || fg.qty,
        reqd: 1
    }));

    const d = new frappe.ui.Dialog({
        title: 'Confirm Real Quantities (Handle Damage)',
        fields,
        primary_action_label: 'Confirm',
        primary_action(values) {
            frm.doc.finish_goods.forEach((fg, idx) => {
                let new_qty = values[`real_qty_${idx}`];
                fg.real_qty = new_qty;
                fg.qty = new_qty;

               
                const main_batch = frm.doc.main_batches.find(b => b.finish_good_index === fg.finish_good_index);
                if (main_batch) {
                    if (!main_batch.original_parts_qty) {
                        main_batch.original_parts_qty = main_batch.parts_qty || 0;
                    }

                    main_batch.parts_qty = new_qty;
                }

                const related_batches = frm.doc.other_batches.filter(
                    ob => ob.finish_good_index === fg.finish_good_index
                );
                const group_map = {};
                for (let ob of related_batches) {
                    const key = ob.batch_number_check || 0;
                    if (!group_map[key]) group_map[key] = [];
                    group_map[key].push(ob);
                }

                for (const key of Object.keys(group_map)) {
                    const group = group_map[key];

                    const total_in_group = group.reduce((sum, ob) => sum + (ob.qty || 0), 0);
                    if (total_in_group <= new_qty) {
                        
                        group.forEach(ob => {
                            if (!ob.original_parts_qty) {
                                ob.original_parts_qty = ob.qty || 0;
                            }
                        });
                        continue;
                    }

                    let remaining = new_qty;
                    for (let i = 0; i < group.length; i++) {
                        let ob = group[i];
                        if (!ob.original_parts_qty) {
                            ob.original_parts_qty = ob.qty || 0;
                        }
                        const available = ob.qty || 0;
                        if (remaining >= available) {
                            remaining -= available;
                        } else {
                            ob.qty = remaining;
                            remaining = 0;
                            for (let j = i + 1; j < group.length; j++) {
                                if (!group[j].original_parts_qty) {
                                    group[j].original_parts_qty = group[j].qty || 0;
                                }
                                group[j].qty = 0;
                            }
                            break;
                        }
                    }
                }
            });
            frm.doc.other_batches.forEach(ob => {
                ob.new_qty_pivot = ob.qty;
            });
            

            frm.refresh_field('finish_goods');
            frm.refresh_field('main_batches');
            frm.refresh_field('other_batches');
            d.hide();

            frappe.msgprint('Real quantities updated. Extra parts were trimmed based on batch grouping.');
        }
    });

    d.show();
}

frappe.ui.form.on('Assemblying', {
    onload: function(frm) {
        if (!frm.is_new()) return;

        frappe.db.get_doc('Stitch Settings', 'Stitch Settings')
            .then(settings => {
                frm.set_value('distination_warehouse', settings.distination_warehouse || '');
                frm.set_value('damage_parts_warehouse', settings.damage_parts_warehouse || '');
                frm.set_value('workers_account', settings.assembling_workers_account || '');
                frm.set_value('project', settings.assembling_project || '');
                frm.set_value('assembly_extra_cost_account', settings.assembly_extra_cost_account || '');
                
            })
            .catch(err => {
                console.error('[Assemblying] Failed to load Stitch Settings:', err);
                frappe.msgprint(__('Error loading default settings from Stitch Settings.'));
            });
    }
});
