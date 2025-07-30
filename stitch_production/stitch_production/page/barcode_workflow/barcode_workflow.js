frappe.pages['barcode-workflow'].on_page_load = function(wrapper) {
    var page = frappe.ui.make_app_page({
        parent: wrapper,
        title: 'Stitching Operation',
        single_column: true
    });

    $(wrapper).html(`
        <div class="container py-4">
            <div class="row mb-4">
                <div class="col-md-6 offset-md-3">
                    <div class="card shadow-sm rounded-3">
                        <div class="card-body">
                            <h4 class="card-title mb-3 text-center">Scan Batch</h4>
                            <input type="text" id="barcode_input" class="form-control form-control-lg" placeholder="Scan Barcode..." autofocus />
                        </div>
                    </div>
                </div>
            </div>
        
            <div class="row">
                <div class="col-md-6 offset-md-3">
                    <div class="card shadow-sm rounded-3">
                        <div class="card-body">
                            <h4 class="card-title mb-3 text-center">Scan Assembly</h4>
                            <input type="text" id="barcode_input_assembly" class="form-control form-control-lg" placeholder="Scan Barcode..." autofocus />
                        </div>
                    </div>
                </div>
            </div>
        </div>
    `);
    

    setTimeout(() => $('#barcode_input').focus(), 300);
    setTimeout(() => $('#barcode_input_assembly').focus(), 300);

    $('#barcode_input').on('keypress', function(e) {
        if (e.which === 13) {
            const barcode = $(this).val().trim();
            $(this).val('');

            if (!barcode) return;

            frappe.call({
                method: 'stitch_production.api.get_post_assembly_by_barcode',
                args: { barcode },
                callback: function(r) {
                    if (!r.message) {
                        frappe.msgprint(__('No document found for barcode: ') + barcode);
                        return;
                    }

                    const currentDoc = r.message;
                    const status = currentDoc.status || 'Assembly';
                    const name = currentDoc.name;

                    frappe.confirm(
                        `<b>Post Assembly:</b> ${name}<br>
                         <b>Current Status:</b> ${status}<br><br>
                         Do you want to advance to the next step?`,
                        () => {
                            frappe.call({
                                method: 'stitch_production.api.advance_stitching_step',
                                args: { docname: name },
                                callback: function(res) {
                                    if (!res.message) {
                                        frappe.msgprint('Could not advance step.');
                                        return;
                                    }
                        
                                    if (res.message.final_step) {
                                        frappe.prompt([
                                            {
                                                label: `Final Qty for ${res.message.item}`,
                                                fieldname: "qty",
                                                fieldtype: "Float",
                                                default: res.message.qty,
                                                reqd: 1
                                            }
                                        ],
                                        (values) => {
                                            frappe.call({
                                                method: 'stitch_production.api.advance_stitching_step',
                                                args: {
                                                    docname: name,
                                                    final_qty: values.qty
                                                },
                                                callback: function(r2) {
                                                    frappe.show_alert({ message: r2.message?.message || 'Submitted', indicator: 'green' });
                                                }
                                            });
                                        },
                                        __("Final Step - Confirm Receipt Qty"));
                                    } else {
                                        frappe.show_alert({
                                            message: `Step updated: ${res.message.message || res.message}`,
                                            indicator: 'green'
                                        });
                                    }
                                }
                            });
                        },                                                
                        () => {
                            frappe.show_alert({
                                message: `Step not updated.`,
                                indicator: 'orange'
                            });
                        }
                    );
                }
            });
        }
    });

    $('#barcode_input_assembly').on('keypress', function (e) {
        if (e.which === 13) {
            const barcode = $(this).val().trim();
            $(this).val('');
    
            if (!barcode) return;
    
            frappe.call({
                method: 'stitch_production.api.get_post_assemblies_by_assembly_barcode',
                args: { barcode },
                callback: function (r) {
                    if (!r.message || r.message.posts.length === 0) {
                        frappe.msgprint(__('No Post Assembly documents found for this operation.'));
                        return;
                    }
    
                    const posts = r.message.posts;
    
                    let html = `
                        <div class="p-4 bg-light rounded shadow-sm border">
                            <h5 class="mb-4 text-primary">Assembly: <strong>${r.message.assembly}</strong></h5>
                            <div class="table-responsive">
                                <table class="table table-striped table-bordered align-middle text-center">
                                    <thead class="table-primary">
                                        <tr>
                                            <th scope="col">Post Assembly</th>
                                            <th scope="col">Status</th>
                                            <th scope="col">Finished</th>
                                            <th scope="col">Qty</th>
                                            <th scope="col">Barcode</th>
                                        </tr>
                                    </thead>
                                    <tbody>
                    `;
    
                    posts.forEach(post => {
                        html += `
                            <tr>
                                <td>${post.name}</td>
                                <td>${post.status}</td>
                                <td>${post.finished}</td>
                                <td>${post.qty}</td>
                                <td>${post.barcode || ''}</td>
                            </tr>
                        `;
                    });
    
                    html += `
                                    </tbody>
                                </table>
                            </div>
                        </div>
                    `;
    
                    if ($('#post-assembly-table').length) {
                        $('#post-assembly-table').html(html);
                    } else {
                        $(wrapper).append(`<div id="post-assembly-table" class="mt-4">${html}</div>`);
                    }
                }
            });
        }
    });
    
    
};
