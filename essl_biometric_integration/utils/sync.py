from datetime import timedelta

import frappe
from frappe.utils import now_datetime

from essl_biometric_integration.utils.soap_client import EsslApiError, EsslConnectionError, get_transactions

SYNC_INTERVAL_MINUTES = 30


def enqueue_sync_all_devices() -> None:
	"""Scheduler entry point. Enqueues one RQ job per enabled device that is due for sync."""
	try:
		settings = frappe.get_single("eSSL Integration Settings")
	except Exception:
		return

	if not settings.base_url or not settings.username:
		return

	now = now_datetime()

	for device in settings.devices:
		if not device.enabled:
			continue

		if device.last_synced_at:
			elapsed_minutes = (now - device.last_synced_at).total_seconds() / 60
			if elapsed_minutes < SYNC_INTERVAL_MINUTES:
				continue

		frappe.enqueue(
			"essl_biometric_integration.utils.sync.sync_device",
			device_name=device.name,
			queue="long",
			timeout=600,
		)


def sync_device(device_name: str) -> None:
	"""RQ job entry point. Fetches logs for one device and pushes to Frappe HR."""
	settings = frappe.get_single("eSSL Integration Settings")
	device = frappe.get_doc("eSSL Device", device_name)

	now = now_datetime()

	if device.last_synced_at:
		from_dt = device.last_synced_at.strftime("%Y-%m-%d")
	else:
		from_dt = (now - timedelta(days=1)).strftime("%Y-%m-%d")

	to_dt = now.strftime("%Y-%m-%d")

	try:
		logs = get_transactions(
			base_url=settings.base_url,
			username=settings.username,
			password=settings.get_password("password"),
			serial_number=device.serial_number,
			from_dt=from_dt,
			to_dt=to_dt,
		)
	except (EsslConnectionError, EsslApiError) as exc:
		frappe.log_error(str(exc), "eSSL Sync Error")
		raise

	for log in logs:
		try:
			_push_checkin(log["user_id"], log["timestamp"], device.serial_number)
		except frappe.ValidationError:
			pass

	device.db_set("last_synced_at", now)


def _push_checkin(user_id: str, timestamp: str, serial_number: str) -> None:
	"""Push one punch log to Frappe HR. Raises frappe.ValidationError if employee not found."""
	from hrms.hr.doctype.employee_checkin.employee_checkin import add_log_based_on_employee_field

	add_log_based_on_employee_field(
		employee_field_value=user_id,
		timestamp=timestamp,
		device_id=serial_number,
		employee_fieldname="attendance_device_id",
	)
