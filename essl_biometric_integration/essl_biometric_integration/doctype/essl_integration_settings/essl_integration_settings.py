import frappe
from frappe.model.document import Document


class eSSLIntegrationSettings(Document):
	@frappe.whitelist()
	def sync_now(self) -> dict:
		"""Trigger a synchronous (non-queued) sync for all enabled devices. Used for testing."""
		from essl_biometric_integration.utils.sync import sync_device

		if not self.base_url or not self.username:
			frappe.throw("Please configure Base URL and Username before syncing.")

		synced = []
		errors = []
		for device in self.devices:
			if device.enabled:
				label = device.device_label or device.serial_number
				try:
					sync_device(device.name)
					synced.append(label)
				except Exception as exc:
					errors.append({"device": label, "error": str(exc)})

		return {"synced": synced, "errors": errors}
