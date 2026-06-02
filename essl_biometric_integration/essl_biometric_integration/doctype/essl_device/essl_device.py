import frappe
from frappe.model.document import Document


class eSSLDevice(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		device_label: DF.Data
		enabled: DF.Check
		last_synced_at: DF.Date | None
		parent: DF.Data
		parentfield: DF.Data
		parenttype: DF.Data
		serial_number: DF.Data
	# end: auto-generated types

	pass
