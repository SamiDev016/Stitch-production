frappe.pages['barcode-workflow'].on_page_load = function(wrapper) {
    if (!window.html2pdf) {
        const script = document.createElement("script");
        const script2 = document.createElement("script");
        script.src = "https://cdnjs.cloudflare.com/ajax/libs/html2pdf.js/0.10.1/html2pdf.bundle.min.js";
        script2.src = "https://cdn.jsdelivr.net/npm/@tailwindcss/browser@4";
        document.head.appendChild(script);
        document.head.appendChild(script2);
    }

    frappe.ui.make_app_page({
        parent: wrapper,
        title: 'Stitching Operation',
        single_column: true
    });

    $(wrapper).html(`
        <div class="max-w-4xl mx-auto py-6">
            <div class="bg-white shadow rounded-lg p-6 mb-6">
                <h2 class="text-xl font-semibold text-center mb-4">Scan Assembly Operation</h2>
                <input type="text" id="barcode_input_assembly" class="w-full p-3 border border-gray-300 rounded focus:outline-none focus:ring-2 focus:ring-blue-500" placeholder="Scan Barcode..." autofocus />
            </div>
            <div class="bg-white shadow rounded-lg p-6 mb-6">
                <h2 class="text-xl font-semibold text-center mb-4">Scan Batch</h2>
                <input type="text" id="barcode_input" class="w-full p-3 border border-gray-300 rounded focus:outline-none focus:ring-2 focus:ring-blue-500" placeholder="Scan Barcode..." autofocus />
            </div>

            

            <div id="download-button-container" class="hidden text-right mb-4">
                <button id="download-pdf" class="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700 transition">Download Table</button>
            </div>
        </div>
    `);

    setTimeout(() => $('#barcode_input').focus(), 300);
    setTimeout(() => $('#barcode_input_assembly').focus(), 300);

    $('#barcode_input').on('keypress', function (e) {
        if (e.which === 13) {
            const barcode = $(this).val().trim();
            $(this).val('');

            if (!barcode) return;

            frappe.call({
                method: 'stitch_production.api.get_post_assembly_by_barcode',
                args: { barcode },
                callback: function (r) {
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
                                callback: function (res) {
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
                                                    callback: function (r2) {
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

            localStorage.setItem('last_scanned_assembly_barcode', barcode);

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
                        <div class="p-4 bg-white rounded shadow border" id="assembly-content">
                            <h5 class="mb-4 text-xl text-blue-600">Assembly: <strong>${r.message.assembly}</strong></h5>
                            <div class="overflow-x-auto">
                                <table class="min-w-full divide-y divide-gray-200 text-sm text-center border">
                                    <thead class="bg-blue-100 text-blue-800">
                                        <tr>
                                            <th class="px-4 py-2">Step</th>
                                            <th class="px-4 py-2">Finished</th>
                                            <th class="px-4 py-2">Qty</th>
                                            <th class="px-4 py-2">Barcode</th>
                                        </tr>
                                    </thead>
                                    <tbody class="divide-y divide-gray-100">
                    `;

                    posts.forEach(post => {
                        html += `
                            <tr class="hover:bg-gray-50">
                                <td class="px-4 py-2">${post.status}</td>
                                <td class="px-4 py-2">${post.finished}</td>
                                <td class="px-4 py-2">${post.qty}</td>
                                <td class="px-4 py-2">${post.barcode || ''}</td>
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

                    $('#download-button-container').removeClass('hidden');

                    setTimeout(() => {
                        $('#download-pdf').off('click').on('click', function () {
                            const element = document.getElementById('post-assembly-table');
                            if (!element) return;

                            const opt = {
                                margin: 0.5,
                                filename: 'assembly-report.pdf',
                                image: { type: 'jpeg', quality: 0.98 },
                                html2canvas: { scale: 2 },
                                jsPDF: { unit: 'in', format: 'letter', orientation: 'portrait' }
                            };

                            html2pdf().from(element).set(opt).save();
                        });
                    }, 300);
                }
            });
        }
    });

    const lastScanned = localStorage.getItem('last_scanned_assembly_barcode');
    if (lastScanned) {
        $('#barcode_input_assembly').val(lastScanned).trigger({ type: 'keypress', which: 13 });
    }
};
