// Parent doctype: Cutting Operation
frappe.ui.form.on('cutting operation', {
  refresh(frm) {
    console.log('[Cutting Operation] refreshed');
  }
});

// Child-table doctype: Cutting Rolls
frappe.ui.form.on('Cutting Rolls', {
  // 1) When barcode is scanned into roll_barcode
  roll_barcode(frm, cdt, cdn) {
    const row = locals[cdt][cdn];
    let raw = row.roll_barcode || '';
    console.log('[Cutting Rolls] raw barcode field:', raw);

    // 1a) Strip any HTML tags
    let bc = raw.replace(/<[^>]*>/g, '').trim();
    console.log('[Cutting Rolls] after strip tags:', bc);

    // 1b) If still empty, read the data-barcode-value attribute from rendered SVG
    if (!bc) {
      const wrapper = frm.fields_dict.used_rolls.grid
        .grid_rows_by_docname[cdn]
        .fields_dict.roll_barcode.$wrapper;
      bc = wrapper.find('svg').attr('data-barcode-value') || '';
      console.log('[Cutting Rolls] from data-barcode-value:', bc);
    }

    if (!bc) {
      console.warn('[Cutting Rolls] No barcode value found, skipping lookup');
      return;
    }

    // 2) Lookup by serial_number_barcode
    frappe.db.get_value('Rolls',
      { serial_number_barcode: bc },
      ['name','weight','color']
    ).then(res => {
      console.log('[Cutting Rolls] lookup response:', res);
      const m = res.message || {};
      if (!m.name) {
        frappe.msgprint(__('No Roll found with barcode {0}', [bc]));
        return;
      }
      console.log('[Cutting Rolls] Populating fields from:', m);
      frappe.model.set_value(cdt, cdn, 'roll',     m.name);
      frappe.model.set_value(cdt, cdn, 'used_qty', m.weight || 0);
      frappe.model.set_value(cdt, cdn, 'color',    m.color   || '');
    }).catch(err => {
      console.error('[Cutting Rolls] Error fetching Rolls:', err);
      frappe.msgprint(__('Error looking up roll — see console.'));
    });
  },

  // 3) When user picks a roll manually
  roll(frm, cdt, cdn) {
    const row = locals[cdt][cdn];
    console.log('[Cutting Rolls] roll selected:', row.roll);
    if (row.roll && (!row.used_qty || row.used_qty === 0)) {
      frappe.db.get_value('Rolls', row.roll, 'weight')
        .then(res => {
          console.log('[Cutting Rolls] roll weight:', res);
          const wt = res.message.weight || 0;
          frappe.model.set_value(cdt, cdn, 'used_qty', wt);
        })
        .catch(err => console.error('[Cutting Rolls] weight lookup error:', err));
    }
  },

  // 4) Clamp used_qty to roll's available weight
  used_qty(frm, cdt, cdn) {
    const row = locals[cdt][cdn];
    console.log('[Cutting Rolls] used_qty changed:', row.used_qty);
    if (!row.roll) {
      console.warn('[Cutting Rolls] No roll selected, skipping clamp');
      return;
    }
    frappe.db.get_value('Rolls', row.roll, 'weight')
      .then(res => {
        const max = res.message.weight || 0;
        console.log('[Cutting Rolls] max weight:', max);
        if (row.used_qty > max) {
          frappe.msgprint({
            title: __('Too much!'),
            message: __('You can’t use more than {0} kg from roll {1}', [max, row.roll]),
            indicator: 'red'
          });
          frappe.model.set_value(cdt, cdn, 'used_qty', max);
        }
      })
      .catch(err => console.error('[Cutting Rolls] clamp lookup error:', err));
  }

});