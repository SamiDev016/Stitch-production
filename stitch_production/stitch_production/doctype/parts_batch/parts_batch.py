import frappe
from frappe.model.document import Document
import math
from functools import reduce

class PartsBatch(Document):
    def before_cancel(self):
        frappe.flags.ignore_linked_with = True

