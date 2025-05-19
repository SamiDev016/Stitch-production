// 1) Whenever the BOM or Quantity changes, refill the Production Materials table
frappe.ui.form.on('Production Operation', {
  poduction_bom(frm) {
    populate_raw_materials(frm);
  },
  produced_quantity(frm) {
    populate_raw_materials(frm);
  }
});

// Helper function to load BOM items into raw_materials
function populate_raw_materials(frm) {
  // if no BOM chosen, clear the table
  if (!frm.doc.poduction_bom) {
    frm.clear_table('raw_materials');
    frm.refresh_field('raw_materials');
    return;
  }

  // Fetch the BOM record
  frappe.call({
    method: 'frappe.client.get',
    args: {
      doctype: 'BOM',
      name: frm.doc.poduction_bom
    },
    callback: function(r) {
      if (!r.message) return;
      const bom = r.message;

      // Clear existing child rows
      frm.clear_table('raw_materials');

      // Append one row per BOM item
      bom.items.forEach(item => {
        const row = frm.add_child('raw_materials');
        row.material          = item.item_code;
        // Calculate required qty = BOM qty × produced_quantity / BOM base qty
        row.required_quantity = ((item.qty || 0) * (frm.doc.produced_quantity || 0)) / (bom.quantity || 1);
      });

      frm.refresh_field('raw_materials');
    }
  });
}

// 2) In each Production Materials row, when you pick Material, filter Batch No
frappe.ui.form.on('Production Materials', {
  material(frm, cdt, cdn) {
    const row = locals[cdt][cdn];

    // Clear any batch previously chosen
    frappe.model.set_value(cdt, cdn, 'batch_no', null);
    frappe.model.set_value(cdt, cdn, 'exist_qty', null); // Clear existing quantity

    // Only show batches for that material
    frm.set_query('batch_no', 'raw_materials', () => ({
      filters: { item: row.material }
    }));
  },

  batch_no(frm, cdt, cdn) {
    const row = locals[cdt][cdn];

    // Ensure material is selected before batch
    if (!row.material) {
      frappe.msgprint(__('Please select a Material before selecting a Batch.'));
      frappe.model.set_value(cdt, cdn, 'batch_no', null);
      frappe.model.set_value(cdt, cdn, 'exist_qty', null); // Clear existing qty if no material
      return;
    }

    // Fetch the batch_qty from the selected batch
    frappe.call({
      method: "frappe.client.get_list",
      args: {
        doctype: "Batch",
        filters: {
          name: row.batch_no,
          item: row.material
        },
        fields: ["batch_qty"],
        limit_page_length: 1
      },
      callback: function (r) {
        let qty = 0;

        if (r.message && r.message.length > 0) {
          qty = r.message[0].batch_qty || 0;
        }

        // Set the existing quantity (exist_qty) field in the child row
        frappe.model.set_value(cdt, cdn, 'exist_qty', qty);
      }
    });
  }
});

// 3) Make sure new child-rows also have the same Batch filter
frappe.ui.form.on('Production Operation', {
  onload_post_render(frm) {
    const grid = frm.fields_dict['raw_materials'];
    if (!grid) return;

    grid.grid.get_field('batch_no').get_query = (doc, cdt, cdn) => {
      const row = locals[cdt][cdn];
      return {
        filters: { item: row.material }
      };
    };
  }
});
