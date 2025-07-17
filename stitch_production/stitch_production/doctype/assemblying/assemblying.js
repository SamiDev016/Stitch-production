function setup_main_bom_query(frm) {
    frm.set_df_property("main_bom", "hidden", 1);

    if (frm.doc.main_operation) {
        frappe.call({
            method: "frappe.client.get",
            args: {
                doctype: "cutting operation",
                name: frm.doc.main_operation
            },
            callback: function(r) {
                if (!r.message) return;

                let bom_list = (r.message.parent_boms || []).map(row => row.parent_bom);

                if (bom_list.length) {
                    frm.set_df_property("main_bom", "hidden", 0);

                    frm.set_query("main_bom", function() {
                        return {
                            filters: [
                                ["name", "in", bom_list]
                            ]
                        };
                    });
                } else {
                    frappe.msgprint("No BOMs linked to the selected Main Operation.");
                }
            }
        });
    }
}

frappe.ui.form.on("Assemblying", {
    onload_post_render(frm) {
        setup_main_bom_query(frm);
    },
    main_operation: function(frm) {
        setup_main_bom_query(frm);
    }
});

frappe.ui.form.on("Assemblying", {
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
                            callback: function(r) {
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
    }
});
