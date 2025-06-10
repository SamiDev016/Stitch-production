let debounceTimer = null;

frappe.ui.form.on('Cutting Rolls', {
    roll_barcode(frm, cdt, cdn) {
        clearTimeout(debounceTimer); 
        debounceTimer = setTimeout(() => {
            const row = locals[cdt][cdn];
            let raw = row.roll_barcode || '';
            console.log('[Cutting Rolls] raw barcode field:', raw);

            let bc = raw.replace(/<[^>]*>/g, '').trim();
            console.log('[Cutting Rolls] after strip tags:', bc);

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

            frappe.db.get_value('Rolls',
                { serial_number_barcode: bc },
                ['name', 'weight', 'color']
            ).then(res => {
                console.log('[Cutting Rolls] lookup response:', res);
                const m = res.message || {};
                if (!m.name) {
                    frappe.msgprint(__('No Roll found with barcode {0}', [bc]));
                    return;
                }
                console.log('[Cutting Rolls] Populating fields from:', m);
                frappe.model.set_value(cdt, cdn, 'roll', m.name);
                frappe.model.set_value(cdt, cdn, 'used_qty', m.weight || 0);
                frappe.model.set_value(cdt, cdn, 'color', m.color || '');
                frappe.model.set_value(cdt, cdn, 'roll_barcode', bc);
            }).catch(err => {
                console.error('[Cutting Rolls] Error fetching Rolls:', err);
                frappe.msgprint(__('Error looking up roll — see console.'));
            });
        }, 300);
    },

    roll(frm, cdt, cdn) {
        const row = locals[cdt][cdn];
        console.log('[Cutting Rolls] roll selected:', row.roll);
        if (!row.roll) {
            return;
        }

        frappe.db.get_value('Rolls', row.roll, ['weight', 'color', 'serial_number_barcode'])
            .then(res => {
                console.log('[Cutting Rolls] roll data:', res);
                const m = res.message || {};
                const wt = m.weight || 0;
                const col = m.color || '';
                const bc = m.serial_number_barcode || '';

                frappe.model.set_value(cdt, cdn, 'used_qty', wt);
                frappe.model.set_value(cdt, cdn, 'color', col);
                frappe.model.set_value(cdt, cdn, 'roll_barcode', bc);
            })
            .catch(err => console.error('[Cutting Rolls] roll lookup error:', err));
    },

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

