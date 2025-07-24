frappe.pages['barcode-workflow'].on_page_load = function(wrapper) {
    var page = frappe.ui.make_app_page({
        parent: wrapper,
        title: '📦 Barcode Workflow',
        single_column: true
    });

    $(wrapper).html(`
        <div class="barcode-container" style="max-width:800px;margin:auto;padding:20px;">
            <div class="card" style="box-shadow: 0 2px 10px rgba(0,0,0,0.1);">
                <div class="card-body text-center">
                    <h3 class="card-title">📦 WIP Status Update</h3>
                    <p class="text-muted">Scan barcode to update work order status</p>
                    
                    <div class="row mb-4">
                        <div class="col-md-4">
                            <div class="status-card bg-light p-3 rounded" id="stitching-card">
                                <h5>Stitching</h5>
                                <div class="count">0</div>
                            </div>
                        </div>
                        <div class="col-md-4">
                            <div class="status-card bg-light p-3 rounded" id="finishing-card">
                                <h5>Finishing</h5>
                                <div class="count">0</div>
                            </div>
                        </div>
                        <div class="col-md-4">
                            <div class="status-card bg-light p-3 rounded" id="emplaage-card">
                                <h5>Emplaage</h5>
                                <div class="count">0</div>
                            </div>
                        </div>
                    </div>
                    
                    <input type="text" id="barcode_input" class="form-control form-control-lg mb-3" 
                        placeholder="Scan barcode or enter manually..." autofocus />
                    
                    <div id="barcode_result" class="alert d-none mb-3"></div>
                    
                    <div class="d-flex justify-content-between mt-4">
                        <button class="btn btn-outline-secondary" id="manual_status_btn">
                            <i class="fa fa-edit"></i> Manual Status Update
                        </button>
                        <button class="btn btn-outline-primary" id="recent_scans_btn">
                            <i class="fa fa-history"></i> Recent Scans
                        </button>
                    </div>
                </div>
            </div>
            
            <!-- Hidden form for manual status update -->
            <div id="manual_status_form" class="card mt-3 d-none" style="box-shadow: 0 2px 10px rgba(0,0,0,0.1);">
                <div class="card-body">
                    <h5 class="card-title">Manual Status Update</h5>
                    <div class="form-group">
                        <label>Document ID</label>
                        <input type="text" class="form-control" id="manual_doc_id">
                    </div>
                    <div class="form-group">
                        <label>New Status</label>
                        <select class="form-control" id="manual_status">
                            <option value="WIP Stitching">WIP Stitching</option>
                            <option value="WIP Finishing">WIP Finishing</option>
                            <option value="WIP Emplaage">WIP Emplaage</option>
                            <option value="Completed">Completed</option>
                        </select>
                    </div>
                    <button class="btn btn-primary" id="update_status_btn">Update Status</button>
                    <button class="btn btn-outline-secondary ml-2" id="cancel_manual_btn">Cancel</button>
                </div>
            </div>
        </div>
    `);

    // Add some styling
    $('<style>')
        .text(`
            .status-card {
                transition: all 0.3s;
                cursor: pointer;
            }
            .status-card:hover {
                transform: translateY(-3px);
                box-shadow: 0 4px 8px rgba(0,0,0,0.1);
            }
            .status-card h5 {
                color: #6c757d;
            }
            .status-card .count {
                font-size: 24px;
                font-weight: bold;
                color: #007bff;
            }
            #barcode_input {
                font-size: 18px;
                height: 50px;
            }
        `)
        .appendTo('head');

    // Initialize variables
    let recentScans = [];
    let statusCounts = {
        'stitching': 0,
        'finishing': 0,
        'emplaage': 0
    };

    // Fake data for demonstration
    const fakeWorkOrders = {
        'WO-1001': { name: 'WO-1001', status: 'WIP Stitching', item: 'T-Shirt Basic', qty: 50 },
        'WO-1002': { name: 'WO-1002', status: 'WIP Finishing', item: 'Jeans Classic', qty: 30 },
        'WO-1003': { name: 'WO-1003', status: 'WIP Emplaage', item: 'Jacket Winter', qty: 20 },
        'WO-1004': { name: 'WO-1004', status: 'WIP Stitching', item: 'Dress Summer', qty: 40 },
        'WO-1005': { name: 'WO-1005', status: 'Completed', item: 'Shirt Formal', qty: 25 }
    };

    // Update status counts
    function updateStatusCounts() {
        statusCounts = {
            'stitching': 0,
            'finishing': 0,
            'emplaage': 0
        };
        
        for (const wo in fakeWorkOrders) {
            const status = fakeWorkOrders[wo].status;
            if (status === 'WIP Stitching') statusCounts.stitching++;
            if (status === 'WIP Finishing') statusCounts.finishing++;
            if (status === 'WIP Emplaage') statusCounts.emplaage++;
        }
        
        $('#stitching-card .count').text(statusCounts.stitching);
        $('#finishing-card .count').text(statusCounts.finishing);
        $('#emplaage-card .count').text(statusCounts.emplaage);
    }

    // Initialize counts
    updateStatusCounts();

    // Handle barcode input
    $('#barcode_input').on('change', function() {
        const barcode = $(this).val().trim();
        if (!barcode) return;
        
        const resultDiv = $('#barcode_result');
        resultDiv.removeClass('d-none alert-success alert-danger alert-info');
        
        // Find the work order (using fake data)
        if (fakeWorkOrders[barcode]) {
            const wo = fakeWorkOrders[barcode];
            
            // Determine next status
            let newStatus = '';
            if (wo.status === 'WIP Stitching') newStatus = 'WIP Finishing';
            else if (wo.status === 'WIP Finishing') newStatus = 'WIP Emplaage';
            else if (wo.status === 'WIP Emplaage') newStatus = 'Completed';
            else newStatus = wo.status; // no change if already completed
            
            // Update status
            if (newStatus !== wo.status) {
                fakeWorkOrders[barcode].status = newStatus;
                updateStatusCounts();
                
                resultDiv.addClass('alert-success');
                resultDiv.html(`
                    <strong>Success!</strong> Status updated for <strong>${barcode}</strong><br>
                    <strong>Item:</strong> ${wo.item}<br>
                    <strong>Qty:</strong> ${wo.qty}<br>
                    <strong>Old Status:</strong> ${wo.status}<br>
                    <strong>New Status:</strong> ${newStatus}
                `);
                
                // Add to recent scans
                recentScans.unshift({
                    barcode: barcode,
                    item: wo.item,
                    oldStatus: wo.status,
                    newStatus: newStatus,
                    timestamp: new Date()
                });
                if (recentScans.length > 5) recentScans.pop();
            } else {
                resultDiv.addClass('alert-info');
                resultDiv.html(`
                    <strong>No change needed</strong> for <strong>${barcode}</strong><br>
                    <strong>Item:</strong> ${wo.item}<br>
                    <strong>Qty:</strong> ${wo.qty}<br>
                    <strong>Current Status:</strong> ${wo.status}
                `);
            }
        } else {
            resultDiv.addClass('alert-danger');
            resultDiv.html(`<strong>Error!</strong> Work order <strong>${barcode}</strong> not found`);
        }
        
        // Clear input and refocus
        $(this).val('');
        $(this).focus();
    });

    // Manual status update button
    $('#manual_status_btn').on('click', function() {
        $('#manual_status_form').toggleClass('d-none');
        $('#manual_doc_id').focus();
    });

    $('#cancel_manual_btn').on('click', function() {
        $('#manual_status_form').addClass('d-none');
        $('#barcode_input').focus();
    });

    // Update status manually
    $('#update_status_btn').on('click', function() {
        const docId = $('#manual_doc_id').val().trim();
        const newStatus = $('#manual_status').val();
        
        if (!docId) {
            frappe.msgprint('Please enter a document ID');
            return;
        }
        
        if (fakeWorkOrders[docId]) {
            const wo = fakeWorkOrders[docId];
            const oldStatus = wo.status;
            
            // Update status
            fakeWorkOrders[docId].status = newStatus;
            updateStatusCounts();
            
            // Show success message
            frappe.msgprint({
                title: __('Success'),
                indicator: 'green',
                message: __(`Status updated for ${docId}<br>
                    <strong>Item:</strong> ${wo.item}<br>
                    <strong>Qty:</strong> ${wo.qty}<br>
                    <strong>Old Status:</strong> ${oldStatus}<br>
                    <strong>New Status:</strong> ${newStatus}`)
            });
            
            // Add to recent scans
            recentScans.unshift({
                barcode: docId,
                item: wo.item,
                oldStatus: oldStatus,
                newStatus: newStatus,
                timestamp: new Date()
            });
            if (recentScans.length > 5) recentScans.pop();
            
            // Reset form
            $('#manual_doc_id').val('');
            $('#manual_status_form').addClass('d-none');
            $('#barcode_input').focus();
        } else {
            frappe.msgprint({
                title: __('Error'),
                indicator: 'red',
                message: __('Work order {0} not found', [docId])
            });
        }
    });

    // Show recent scans
    $('#recent_scans_btn').on('click', function() {
        if (recentScans.length === 0) {
            frappe.msgprint('No recent scans available');
            return;
        }
        
        let html = `<div class="recent-scans"><h5>Recent Scans</h5><table class="table table-sm">`;
        html += `<tr><th>Barcode</th><th>Item</th><th>Old Status</th><th>New Status</th><th>Time</th></tr>`;
        
        recentScans.forEach(scan => {
            html += `<tr>
                <td>${scan.barcode}</td>
                <td>${scan.item}</td>
                <td>${scan.oldStatus}</td>
                <td>${scan.newStatus}</td>
                <td>${scan.timestamp.toLocaleTimeString()}</td>
            </tr>`;
        });
        
        html += `</table></div>`;
        
        frappe.msgprint({
            title: 'Recent Scans',
            indicator: 'blue',
            message: html
        });
    });

    // Status card click handlers (for quick filtering)
    $('.status-card').on('click', function() {
        const statusType = $(this).attr('id').replace('-card', '');
        let status = '';
        
        if (statusType === 'stitching') status = 'WIP Stitching';
        else if (statusType === 'finishing') status = 'WIP Finishing';
        else if (statusType === 'emplaage') status = 'WIP Emplaage';
        
        let html = `<div class="status-items"><h5>${status} Items</h5><table class="table table-sm">`;
        html += `<tr><th>Work Order</th><th>Item</th><th>Qty</th></tr>`;
        
        let count = 0;
        for (const wo in fakeWorkOrders) {
            if (fakeWorkOrders[wo].status === status) {
                count++;
                html += `<tr>
                    <td>${wo}</td>
                    <td>${fakeWorkOrders[wo].item}</td>
                    <td>${fakeWorkOrders[wo].qty}</td>
                </tr>`;
            }
        }
        
        if (count === 0) {
            html += `<tr><td colspan="3" class="text-muted">No items found</td></tr>`;
        }
        
        html += `</table></div>`;
        
        frappe.msgprint({
            title: status,
            indicator: 'blue',
            message: html
        });
    });
};
