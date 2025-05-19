frappe.ui.form.on('cutting operation', {
  refresh(frm) {
    toggle_ws(frm);
    bind_add_click(frm);
  }
});

function bind_add_click(frm) {
  // Get the grid object
  const grid = frm.fields_dict.workstation_cost && frm.fields_dict.workstation_cost.grid;
  if (!grid) return;

  // Unbind any previous handler (to avoid duplicates)
  grid.grid_buttons.find('.grid-add-row').off('click.custom');

  // Bind a click handler
  grid.grid_buttons.find('.grid-add-row')
    .on('click.custom', () => {
      // Delay to let the new row actually appear in frm.doc
      setTimeout(() => {
        console.log('➕ clicked Add Row, rows now =', (frm.doc.workstation_cost||[]).length);
        toggle_ws(frm);
      }, 200);
    });
}

function toggle_ws(frm) {
  const count = (frm.doc.workstation_cost || []).length;
  console.log('↳ toggle_ws, count =', count);

  const grid = frm.fields_dict.workstation_cost && frm.fields_dict.workstation_cost.grid;
  if (!grid) {
    console.warn('⚠️ workstation_cost grid not found');
    return;
  }

  const btn = grid.grid_buttons.find('.grid-add-row');
  if (!btn.length) {
    console.warn('⚠️ Add Row button not found');
    return;
  }

  if (count >= 1) {
    console.log('hiding Add Row');
    btn.hide();
  } else {
    console.log('showing Add Row');
    btn.show();
  }
}
