frappe.ui.form.on('Stitching Assembly', {
    onload(frm) {
        frm.set_df_property('main_operation_bom', 'hidden', true);
    },

    main_operation(frm) {
        const op = frm.doc.main_operation;

        if (op) {
            frm.set_df_property('main_operation_bom', 'hidden', false);
            frm.set_value('main_operation_bom', null);

            frappe.call({
                method: 'stitch_production.api.get_boms_for_cutting_operation',
                args: { operation_name: op },
                callback: function(r) {
                    if (r.message && Array.isArray(r.message)) {
                        frm.set_query('main_operation_bom', () => {
                            return {
                                filters: {
                                    name: ['in', r.message]
                                }
                            };
                        });
                    }
                }
            });
        } else {
            frm.set_df_property('main_operation_bom', 'hidden', true);
            frm.set_value('main_operation_bom', null);
        }
    }
});
