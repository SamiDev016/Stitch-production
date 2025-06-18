// JavaScript version of your Python‐style SIZE_MAP
const SIZE_MAP = {
  'XS': 'XS',
  'S': 'S',
  'M': 'M',
  'L': 'L',
  'XL': 'XL',
  'XXL': 'XXL',
  'XXXL': 'XXXL',
  '6': '6 ans',
  '8': '8 ans',
  '10': '10 ans',
  '12': '12 ans',
  '14': '14 ans',
  '16': '16 ans'
};

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
        fieldtype: 'Link',
        options: 'BOM',
        reqd: 1
      },
      {
        label: 'Size',
        fieldname: 'size',
        fieldtype: 'Select',
        options: Object.keys(SIZE_MAP).map(key => ({
          label: SIZE_MAP[key],
          value: key
        })),
        reqd: 1
      },
      {
        label: 'Color',
        fieldname: 'color',
        fieldtype: 'Data',
        reqd: 1
      }
    ],
    primary_action_label: 'Add',
    primary_action(values) {
      d.hide();

      // Find the matching Parts Batch
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
          if (r.length > 1) {
            frappe.msgprint(__('Multiple batches found; please refine your filters.'));
          } else {
            frappe.msgprint(__('No Parts Batch found for those criteria.'));
          }
          return;
        }

        const pb_name = r[0].name;
        const row = frm.add_child('batches');
        row.batch = pb_name;

        // Load the full Parts Batch doc to read its child table `parts`
        frappe.db.get_doc('Parts Batch', pb_name).then(pb_doc => {
          // Collect all qty values from pb_doc.parts
          const qtys = pb_doc.parts.map(p => p.qty).filter(q => q > 0);

          if (qtys.length) {
            // Compute the GCD of the list to find the multiplier
            const multiplier = qtys.reduce((a, b) => gcd(a, b));
            row.existing_qty = multiplier;
          } else {
            row.existing_qty = 0;
          }

          frm.refresh_field('batches');
          frappe.show_alert(`Added Parts Batch: ${pb_name}`, 3);
        });
      });
    }
  });

  d.show();
}
