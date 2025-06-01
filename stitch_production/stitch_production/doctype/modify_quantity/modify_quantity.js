frappe.ui.form.on("Modify Quantity", {
    operation: function(frm) {
        if (!frm.doc.operation) return;

        // Clear existing parts_qty
        frm.clear_table("parts_qty");

        // Call the server to get cutting_parts from the selected operation
        frappe.call({
            method: "frappe.client.get",
            args: {
                doctype: "cutting operation",
                name: frm.doc.operation,
            },
            callback: function(r) {
                if (!r.message) return;

                // Only continue if the operation is submitted
                if (r.message.docstatus !== 1) {
                    frappe.msgprint(__('Selected Cutting Operation isnt finished.'));
                    return;
                }

                const cutting_parts = r.message.cutting_parts || [];

                cutting_parts.forEach(part => {
                    const row = frm.add_child("parts_qty");
                    row.part_name = part.part;
                    row.qty = part.quantity;
                });

                frm.refresh_field("parts_qty");
            }
        });
    }
});
