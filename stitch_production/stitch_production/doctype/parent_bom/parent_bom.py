from frappe.model.document import Document
import frappe
from frappe import _

class ParentBOM(Document):
    def on_submit(self):
        colors = set()

        for row in self.boms:
            if not row.bom:
                continue

            # Get the linked BOM
            bom_doc = frappe.get_doc("BOM", row.bom)

            # Get the finished good item (this is a variant)
            item_code = bom_doc.item
            if not item_code:
                frappe.throw(_("BOM {0} does not have a finished good item.").format(row.bom))

            # Fetch the 'Colour' attribute from Item Variant Attribute
            item_color = frappe.db.get_value(
                "Item Variant Attribute",
                {"parent": item_code, "attribute": "Colour"},
                "attribute_value"
            )

            if not item_color:
                frappe.throw(_("Item {0} (from BOM {1}) does not have a Colour attribute.").format(item_code, row.bom))

            colors.add(item_color)

        if len(colors) > 1:
            frappe.throw(_("All BOMs must have the same 'Colour' for their finished goods."))

        # All colors are the same, assign it to the Parent BOM
        if colors:
            self.color = list(colors)[0]
