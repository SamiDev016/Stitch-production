* Stitching Operations App (Custom Frappe App)
A powerful custom Frappe app tailored for stitching and sewing companies, helping you manage the entire manufacturing process – from purchasing raw tissue materials to delivering the final stitched product.

* Key Features
Custom Purchase Receipt
Purchase raw tissue materials and instantly convert them into usable rolls.

Roll Transfer
Easily transfer rolls across departments or warehouses.

Cutting Operation
Manage cutting of rolls, track batches, and monitor quantities.

Assembly Operation
Assemble components before stitching, including cost-per-unit adjustments.

Stitching Operation
Final stitching and production of finished goods with full traceability.

Damage and Loss Handling
Log and manage damaged or lost stock during operations, auto-adjusting costs per unit.

Bonus / Free Items Handling
Add bonus/free stock entries at zero rate without affecting inventory valuation.

Stock Movement Management
Comprehensive tracking of stock movement between departments with accuracy and transparency.

* Ideal For
Stitching and textile manufacturing companies

Garment factories

Any sewing-based production company using Frappe/ERPNext to manage their operations

🚀 Installation & Usage
Prerequisites
Ensure you have a working Frappe/ERPNext site setup. If not, follow the official Frappe Bench guide.

Step 1: Get the App
cd ~/frappe-bench/apps
git clone https://github.com/your-org/stitching_operations.git
Step 2: Install the App on Your Site
cd ~/frappe-bench
bench --site your-site-name install-app stitching_operations
Replace your-site-name with your actual Frappe site name.

Step 3: Apply Migrations
bench --site your-site-name migrate
Step 4: Start Using the App
You will now find new modules and doctypes inside your Frappe Desk UI, covering:

Purchase → Tissue to Roll Conversion

Stock → Roll Transfers

Manufacturing → Cutting / Assembly / Stitching

Reports and Tracking
