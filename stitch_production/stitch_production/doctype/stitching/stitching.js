// JavaScript version of your Python‑style SIZE_MAP
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
          fieldtype: 'Select',
          options: [],    
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
  
      if (op_name && bom_name) {
        frappe.db.get_list('Parts Batch', {
          filters: {
            source_operation: op_name,
            source_bom:       bom_name
          },
          fields: ['color']
        }).then(list => {
          const colors = Array.from(new Set(
            list.map(r => r.color).filter(c => c)
          ));
          d.fields_dict.color.df.options = colors;
          d.fields_dict.color.refresh();
        });
      }
    });
  
    d.show();
  }
  
