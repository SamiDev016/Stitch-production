  // Compute greatest common divisor
  function gcd(a, b) {
    return b === 0 ? a : gcd(b, a % b);
  }
  
  frappe.ui.form.on('Stitching', {
    refresh(frm) {
      if (!frm.__islocal) {
        frm.add_custom_button('Add Batches', () => show_add_batches_dialog(frm));
      }
    }
  });
  
  function show_add_batches_dialog(frm) {
    const d = new frappe.ui.Dialog({
      title: 'Select a Parts Batch',
      fields: [
        {
          label: 'Operation',
          fieldname: 'operation',
          fieldtype: 'Link',
          options: 'cutting operation',
          reqd: 1
        },
        {
          label: 'BOM',
          fieldname: 'bom',
          fieldtype: 'Select',
          options: [],    
          reqd: 1
        },
        {
          label: 'Size',
          fieldname: 'size',
          fieldtype: 'Select',
          options: [], 
          reqd: 1
        },
        {
          label: 'Color',
          fieldname: 'color',
          fieldtype: 'Select',
          options: [],     
          reqd: 1
        }
      ],
      primary_action_label: 'Add',
      primary_action(values) {
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
          if (r.length !== 1) {
            frappe.msgprint(r.length > 1
              ? __('Multiple batches found; please refine your filters.')
              : __('No Parts Batch found for those criteria.'));
            return;
          }
  
          const pb_name = r[0].name;
          const row = frm.add_child('batches');
          row.batch = pb_name;
  
          frappe.db.get_doc('Parts Batch', pb_name).then(pb_doc => {
            const qtys = pb_doc.parts.map(p => p.qty).filter(q => q > 0);
            row.existing_qty = qtys.length
              ? qtys.reduce((a, b) => gcd(a, b))
              : 0;
  
            frm.refresh_field('batches');
            frappe.show_alert(`Added Parts Batch: ${pb_name}`, 3);
          });
        });
      }
    });
  
    d.fields_dict.operation.$input.on('change', () => {
      const op_name = d.get_value('operation');
      d.fields_dict.bom.df.options = [];
      d.fields_dict.bom.refresh();
      d.fields_dict.color.df.options = [];
      d.fields_dict.color.refresh();
  
      if (op_name) {
        frappe.db.get_doc('cutting operation', op_name).then(op_doc => {
          const bom_list = (op_doc.parent_boms || [])
            .map(r => r.parent_bom)
            .filter(Boolean);
          d.fields_dict.bom.df.options = bom_list;
          d.fields_dict.bom.refresh();
        });
      }
    });
  
    d.fields_dict.bom.$input.on('change', () => {
      const op_name  = d.get_value('operation');
      const bom_name = d.get_value('bom');

      d.fields_dict.color.df.options = [];
      d.fields_dict.color.refresh();
      d.fields_dict.size.df.options = [];
      d.fields_dict.size.refresh();

      if (op_name && bom_name) {
        frappe.db.get_list('Parts Batch', {
          filters: {
            source_operation: op_name,
            source_bom:       bom_name
          },
          fields: ['color', 'size']
        }).then(list => {
          const colors = Array.from(new Set(
            list.map(r => r.color).filter(c => c)
          ));
          d.fields_dict.color.df.options = colors;
          d.fields_dict.color.refresh();

          const sizes = Array.from(new Set(
            list.map(r => r.size).filter(s => s)
          ));
          d.fields_dict.size.df.options = sizes;
          d.fields_dict.size.refresh();
        });
      }
    });
  
    d.show();
  }
  let stitchingBarcodeDebounce = null;

frappe.ui.form.on('Assemby Batches', {
  barcode(frm, cdt, cdn) {
    clearTimeout(stitchingBarcodeDebounce);
    stitchingBarcodeDebounce = setTimeout(() => {
      const row = locals[cdt][cdn];
      let raw = row.barcode || '';
      console.log('[Assemby Batches] Raw barcode:', raw);

      let bc = raw.replace(/<[^>]*>/g, '').trim();
      if (!bc) {
        const wrapper = frm.fields_dict.batches.grid
          .grid_rows_by_docname[cdn]
          .fields_dict.barcode?.$wrapper;
        bc = wrapper?.find('svg').attr('data-barcode-value') || '';
        console.log('[Assemby Batches] From SVG fallback:', bc);
      }

      if (!bc) {
        console.warn('[Assemby Batches] No barcode value found.');
        return;
      }

      frappe.db.get_value('Parts Batch', { serial_number_barcode: bc }, 'name')
        .then(res => {
          const pb_name = res.message?.name;
          if (!pb_name) {
            frappe.msgprint(__('No Parts Batch found with barcode: {0}', [bc]));
            return;
          }

          console.log('[Assemby Batches] Found Parts Batch:', pb_name);

          // Set batch field
          frappe.model.set_value(cdt, cdn, 'batch', pb_name);

          // Get full Parts Batch document
          frappe.db.get_doc('Parts Batch', pb_name).then(pb_doc => {
            const parts = pb_doc.parts || [];
            const qtys = parts.map(p => p.qty).filter(q => q > 0);
            const existing_qty = qtys.length ? qtys.reduce((a, b) => gcd(a, b)) : 0;

            console.log(`[Assemby Batches] Computed existing_qty: ${existing_qty} from parts:`, qtys);

            frappe.model.set_value(cdt, cdn, 'existing_qty', existing_qty);
            frm.refresh_field('batches');
            frappe.show_alert(`✔ Loaded Parts Batch ${pb_name}`, 2);
          });
        })
        .catch(err => {
          console.error('[Assemby Batches] Barcode lookup error:', err);
          frappe.msgprint(__('Error loading Parts Batch. See console.'));
        });
    }, 300);
  }
});

// GCD function (must be global)
function gcd(a, b) {
  return b === 0 ? a : gcd(b, a % b);
}
