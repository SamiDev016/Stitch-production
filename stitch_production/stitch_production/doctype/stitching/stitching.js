// Compute greatest common divisor
function gcd(a, b) {
    return b === 0 ? a : gcd(b, a % b);
}

frappe.ui.form.on('Stitching', {
    refresh(frm) {
        console.log('[Stitching] refresh called', frm.docname);
        if (!frm.__islocal) {
            frm.add_custom_button('Add Batches', () => {
                console.log('[Stitching] Add Batches button clicked');
                show_add_batches_dialog(frm);
            });
        }
    }
});

function show_add_batches_dialog(frm) {
    console.log('[Stitching Dialog] show_add_batches_dialog() called');

    const d = new frappe.ui.Dialog({
        title: 'Select a Parts Batch',
        fields: [
            { label: 'Operation', fieldname: 'operation', fieldtype: 'Link',   options: 'cutting operation', reqd: 1 },
            { label: 'BOM',       fieldname: 'bom',       fieldtype: 'Select', options: [],                   reqd: 1 },
            { label: 'Size',      fieldname: 'size',      fieldtype: 'Select', options: [],                   reqd: 1 },
            { label: 'Color',     fieldname: 'color',     fieldtype: 'Select', options: [],                   reqd: 1 }
        ],
        primary_action_label: 'Add',
        primary_action(values) {
            console.log('[Stitching Dialog] primary_action()', values);
            d.hide();

            frappe.db.get_list('Parts Batch', {
                filters: {
                    source_operation: values.operation,
                    source_bom:       values.bom,
                    size:             values.size,
                    color:            values.color
                },
                fields: ['name'],
                limit: 1
            }).then(r => {
                console.log('[Stitching Dialog] get_list result:', r);
                if (r.length !== 1) {
                    frappe.msgprint(r.length > 1
                        ? __('Multiple batches found; please refine your filters.')
                        : __('No Parts Batch found for those criteria.'));
                    return;
                }

                const pb_name = r[0].name;
                console.log('[Stitching Dialog] selected Parts Batch:', pb_name);

                const row = frm.add_child('batches');
                row.batch = pb_name;

                frappe.db.get_doc('Parts Batch', pb_name).then(pb_doc => {
                    console.log('[Stitching Dialog] fetched Parts Batch doc:', pb_doc);
                    const qtys = (pb_doc.parts || []).map(p => p.qty).filter(q => q > 0);
                    const existing_qty = qtys.length ? qtys.reduce((a, b) => gcd(a, b)) : 0;
                    console.log('[Stitching Dialog] computed existing_qty:', existing_qty, 'from', qtys);

                    row.existing_qty = existing_qty;
                    frm.refresh_field('batches');
                    frappe.show_alert(`Added Parts Batch: ${pb_name}`, 3);
                });
            }).catch(err => {
                console.error('[Stitching Dialog] error in primary_action get_list:', err);
                frappe.msgprint(__('Error fetching Parts Batch — see console.'));
            });
        }
    });

    // Handler to fetch BOM options
    const on_operation_change = () => {
        const op = d.get_value('operation');
        console.log('[Stitching Dialog] operation selected:', op);

        // clear BOM/Size/Color
        ['bom','size','color'].forEach(fn => {
            d.fields_dict[fn].df.options = [];
            d.fields_dict[fn].refresh();
        });

        if (!op) return;

        frappe.db.get_doc('cutting operation', op).then(op_doc => {
            console.log('[Stitching Dialog] fetched cutting operation:', op_doc);
            const bom_list = (op_doc.parent_boms || []).map(r => r.parent_bom).filter(Boolean);
            console.log('[Stitching Dialog] parent_boms list:', bom_list);

            d.fields_dict.bom.df.options = bom_list;
            d.fields_dict.bom.refresh();
            // force refresh for chosen/select2
            d.fields_dict.bom.$input.trigger('chosen:updated');
        }).catch(err => {
            console.error('[Stitching Dialog] error fetching cutting operation:', err);
            frappe.msgprint(__('Could not fetch Cutting Operation — see console.'));
        });
    };

    // Bind ALL possible change events on the Link field:
    const op_input = d.fields_dict.operation.$input;
    ['change', 'select2:select', 'autocompleteselect', 'focusout'].forEach(evt => {
        op_input.on(evt, on_operation_change);
    });

    // When BOM changes, fetch Size/Color
    d.fields_dict.bom.$input.on('change', () => {
        const op  = d.get_value('operation');
        const bom = d.get_value('bom');
        console.log('[Stitching Dialog] bom selected:', bom, 'after operation:', op);

        ['size','color'].forEach(fn => {
            d.fields_dict[fn].df.options = [];
            d.fields_dict[fn].refresh();
        });

        if (op && bom) {
            frappe.db.get_list('Parts Batch', {
                filters: { source_operation: op, source_bom: bom },
                fields: ['size','color']
            }).then(list => {
                console.log('[Stitching Dialog] get_list for size/color:', list);
                const sizes  = Array.from(new Set(list.map(r => r.size).filter(s => s)));
                const colors = Array.from(new Set(list.map(r => r.color).filter(c => c)));
                console.log('[Stitching Dialog] computed sizes:', sizes, 'colors:', colors);

                d.fields_dict.size.df.options  = sizes;
                d.fields_dict.size.refresh();
                d.fields_dict.color.df.options = colors;
                d.fields_dict.color.refresh();
            }).catch(err => {
                console.error('[Stitching Dialog] error fetching size/color:', err);
                frappe.msgprint(__('Could not fetch Size/Color — see console.'));
            });
        }
    });

    d.show();
}


// Barcode lookup in the child table Assemby Batches
let stitchingBarcodeDebounce = null;

frappe.ui.form.on('Assemby Batches', {
    barcode(frm, cdt, cdn) {
        clearTimeout(stitchingBarcodeDebounce);
        stitchingBarcodeDebounce = setTimeout(() => {
            const row = locals[cdt][cdn];
            let bc = (row.barcode || '').replace(/<[^>]*>/g, '').trim();

            if (!bc) {
                const wrapper = frm.fields_dict.batches.grid
                    .grid_rows_by_docname[cdn]
                    .fields_dict.barcode.$wrapper;
                bc = wrapper.find('svg').attr('data-barcode-value') || '';
            }

            console.log('[Assemby Batches] lookup barcode:', bc);
            if (!bc) return;

            frappe.db.get_value('Parts Batch', { serial_number_barcode: bc }, 'name')
            .then(res => {
                const pb = res.message && res.message.name;
                if (!pb) {
                    frappe.msgprint(__('No Parts Batch found with barcode: {0}', [bc]));
                    return;
                }

                console.log('[Assemby Batches] Found Parts Batch:', pb);
                frappe.model.set_value(cdt, cdn, 'batch', pb);

                frappe.db.get_doc('Parts Batch', pb).then(doc => {
                    const qtys = (doc.parts || []).map(p => p.qty).filter(q => q > 0);
                    const existing_qty = qtys.length ? qtys.reduce((a,b) => gcd(a,b)) : 0;
                    console.log('[Assemby Batches] existing_qty:', existing_qty, 'from', qtys);

                    frappe.model.set_value(cdt, cdn, 'existing_qty', existing_qty);
                    frm.refresh_field('batches');
                    frappe.show_alert(`✔ Loaded Parts Batch: ${pb}`, 2);
                });
            })
            .catch(err => {
                console.error('[Assemby Batches] Barcode lookup error:', err);
                frappe.msgprint(__('Error loading Parts Batch. See console.'));
            });
        }, 300);
    }
});
