// Rolls Transfer – Client Script

frappe.ui.form.on('Roll Warehouse', {
  code_bar(frm, cdt, cdn) {
    const row = locals[cdt][cdn];
    let bc = (row.code_bar || '').trim();
    if (!bc) return;

    // 1) If the field contains SVG markup, strip out all tags
    bc = bc.replace(/<[^>]*>/g, '').trim();

    // 2) If that still yields nothing, try reading the
    //    data-barcode-value attribute from the rendered SVG
    if (!bc) {
      const cell = frm.fields_dict.rolls
        .grid.grid_rows_by_docname[cdn]
        .fields_dict.code_bar.$wrapper;
      bc = cell.find('svg').attr('data-barcode-value') || '';
    }

    if (!bc) return;

    // 3) Lookup the Rolls record by serial_number_barcode
    frappe.db.get_value('Rolls',
      { serial_number_barcode: bc },
      ['name','warehouse']
    ).then(res => {
      if (res && res.message) {
        // populate the read-only fields
        frappe.model.set_value(cdt, cdn, 'roll',      res.message.name);
        frappe.model.set_value(cdt, cdn, 'warehouse', res.message.warehouse);
      } else {
        frappe.msgprint({
          title: __('Roll Not Found'),
          indicator: 'red',
          message: __('No Rolls found with barcode {0}', [bc])
        });
        frappe.model.set_value(cdt, cdn, 'roll',      '');
        frappe.model.set_value(cdt, cdn, 'warehouse', '');
      }
    }).catch(err => {
      console.error('Error looking up Rolls by barcode:', err);
      frappe.msgprint(__('Error looking up roll — see console.'));
    });
  }
});
