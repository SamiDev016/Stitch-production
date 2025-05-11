frappe.ui.form.on('Production Operation', {
  validate: function(frm) {
    let workers_total = 0;

    // Sum all cost_per_hour * total_hours from workers_cost table
    (frm.doc.workers_cost || []).forEach(row => {
      const row_cost = (row.cost_per_hour || 0) * (row.total_hours || 0);
      workers_total += row_cost;
    });

    // Add individual cost
    const individual_cost = frm.doc.individual_cost || 0;
    const total_cost = workers_total + individual_cost;

    // Set total_cost field
    frm.set_value('total_cost', total_cost);
  }
});
