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
