function sync_items(frm) {
  frm.clear_table('items');

  const agg = {};
  (frm.doc.custom_rolls || []).forEach(r => {
    const wh = r.warehouse || frm.doc.warehouse;
    const key = [r.fabric_item, r.price_per_qty, wh].join('|');
    if (!agg[key]) {
      agg[key] = {
        fabric_item:  r.fabric_item,
        price_per_qty: r.price_per_qty,
        warehouse:    wh,
        qty:          0
      };
    }
    agg[key].qty += (r.weight || 0);
  });

  Object.values(agg).forEach(item => {
    const it = frm.add_child('items');
    it.item_code = item.fabric_item;
    it.qty       = item.qty;
    it.rate      = item.price_per_qty;
    it.warehouse = item.warehouse;

    frappe.db.get_value('Item', item.fabric_item, ['item_name','stock_uom'])
      .then(({ message }) => {
        if (message) {
          it.item_name = message.item_name;
          it.uom       = message.stock_uom;
          frm.refresh_field('items');
        }
      })
      .catch(err => console.error('[sync_items] frappe.db.get_value error', err));
  });

  frm.refresh_field('items');
}

frappe.ui.form.on('Purchase Receipt', {
  onload(frm) {
    frm.add_custom_button(__('Add Rolls'), () => open_rolls_dialog(frm));

    // Make items table read-only on load
    frm.fields_dict.items.grid.only_sortable();
    frm.fields_dict.items.grid.wrapper.find('.grid-add-row').hide();
    frm.fields_dict.items.grid.wrapper.find('.grid-remove-rows').hide();
  },

  refresh(frm) {
    // Re-add the button to ensure it's always available
    frm.add_custom_button(__('Add Rolls'), () => open_rolls_dialog(frm));

    // Make items table read-only on refresh
    frm.fields_dict.items.grid.df.read_only = 1;
    frm.fields_dict.items.grid.refresh();
  }
});

function open_rolls_dialog(frm) {
  const rolls_warehouse = frm.doc.rolls_warehouse || frm.doc.warehouse;

  const d = new frappe.ui.Dialog({
    title: __('Add Multiple Rolls'),
    fields: [
      { fieldtype: 'Link',      fieldname: 'fabric_item',      options: 'Item',      label: __('Fabric Item'), reqd: 1 },
      { fieldtype: 'Currency',  fieldname: 'price_per_qty',    label: __('Price per Kg'), reqd: 1 },
      { fieldtype: 'Link',      fieldname: 'warehouse',        options: 'Warehouse', label: __('Warehouse'), default: rolls_warehouse },
      { fieldtype: 'Data',      fieldname: 'gsm',              label: __('GSM'), reqd: 1 },
      { fieldtype: 'Float',     fieldname: 'longeur',          label: __('Longueur (Meter)'), reqd: 1 },
      { fieldtype: 'Select',    fieldname: 'turbolantouvert',  label: __('Type'), options: ['Turbolant', 'Ouvert'], reqd: 1 },
      { fieldtype: 'Small Text',fieldname: 'rolls_details',    label: __('Roll Weights (comma-separated)'), placeholder: __('e.g. 20,20,50,10'), reqd: 1 },
    ],
    size: 'small',
    primary_action_label: __('Create Rolls'),
    primary_action(values) {
      try {
        const weights = values.rolls_details
          .split(',')
          .map(w => parseFloat(w.trim()))
          .filter(w => !isNaN(w) && w > 0);

        if (!weights.length) {
          frappe.msgprint(__('Please enter at least one valid weight.'));
          return;
        }

        weights.forEach(w => {
          const r = frm.add_child('custom_rolls');
          r.fabric_item        = values.fabric_item;
          r.weight             = w;
          r.price_per_qty      = values.price_per_qty;
          r.warehouse          = values.warehouse;
          r.longeur            = values.longeur;
          r.turbolantouvert    = values.turbolantouvert;
          r.gsm                = values.gsm;
        });

        frm.refresh_field('custom_rolls');
        sync_items(frm);
        d.hide();
        frappe.msgprint(__('Rolls added successfully'));
      } catch (e) {
        frappe.msgprint(__('An error occurred, check console for details.'));
        console.error(e);
      }
    }
  });

  d.show();
}
