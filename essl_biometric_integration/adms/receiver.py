# essl_biometric_integration/adms/receiver.py
import calendar
import datetime

import frappe
from werkzeug.wrappers import Response

_STATUS_MAP: dict[int, str] = {
	0: "IN",
	1: "OUT",
	4: "IN",
	5: "OUT",
}

_HEARTBEAT_TEMPLATE = (
	"GET OPTION FROM: {sn}\n"
	"ATTLOGStamp={stamp}\n"
	"OPERLOGStamp={stamp}\n"
	"ATTPHOTOStamp={stamp}\n"
	"ErrorDelay=30\n"
	"Delay=10\n"
	"TransTimes=00:00;14:05\n"
	"TransInterval=1\n"
	"TransFlag=TransData AttLog OpLog EnrollUser ChgUser EnrollFP ChgFP UserPic\n"
	"TimeZone=5.5\n"
	"Realtime=1\n"
	"Encrypt=0\n"
)


def handle() -> Response:
	"""Entry point registered via website_route_rules for /iclock/cdata.

	Dispatches GET to handle_heartbeat() and POST to handle_log_upload().
	Always returns HTTP 200 so the device does not enter an error-retry loop.
	"""
	request = frappe.local.request
	try:
		if request.method == "GET":
			body = handle_heartbeat(request)
		elif request.method == "POST":
			body = handle_log_upload(request)
		else:
			body = "OK\n"
	except Exception:
		frappe.log_error(title="eSSL ADMS Error", message=frappe.get_traceback())
		body = ""
	return Response(body, content_type="text/plain; charset=utf-8")


def handle_heartbeat(request) -> str:
	"""Return the ADMS handshake payload for a device heartbeat (GET)."""
	sn: str = request.args.get("SN", "")
	stamp: int = _get_last_adms_stamp(sn)
	return _HEARTBEAT_TEMPLATE.format(sn=sn, stamp=stamp)


def handle_log_upload(request) -> str:
	"""Parse and persist an ADMS attendance batch (POST). Always returns 'OK\\n'."""
	from hrms.hr.doctype.employee_checkin.employee_checkin import add_log_based_on_employee_field

	sn: str = request.args.get("SN", "")
	raw_body: str = request.get_data(as_text=True)
	records = _parse_attlog_body(raw_body)

	success_count = 0
	skip_count = 0
	max_stamp = 0

	for rec in records:
		log_type: str | None = _STATUS_MAP.get(rec["status_code"])
		if log_type is None:
			skip_count += 1
			continue

		try:
			add_log_based_on_employee_field(
				employee_field_value=rec["user_id"],
				timestamp=rec["timestamp_str"],
				device_id=sn,
				log_type=log_type,
				employee_fieldname="attendance_device_id",
			)
			success_count += 1
			if rec["unix_stamp"] > max_stamp:
				max_stamp = rec["unix_stamp"]
		except Exception:
			frappe.logger("essl_biometric_integration").warning(
				"eSSL ADMS: could not create checkin for user_id=%s ts=%s",
				rec["user_id"],
				rec["timestamp_str"],
			)
			skip_count += 1

	if max_stamp > 0:
		_update_last_adms_stamp(sn, max_stamp)

	frappe.logger("essl_biometric_integration").info(
		"eSSL ADMS batch SN=%s: %d created, %d skipped", sn, success_count, skip_count
	)
	return "OK\n"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _parse_attlog_body(raw_body: str) -> list[dict]:
	"""Split raw ADMS POST body into per-record dicts.

	Skips header lines (SN=, table=, Stamp=) and any line without tabs.
	"""
	records = []
	for line in raw_body.splitlines():
		line = line.strip()
		if not line or "\t" not in line:
			continue
		parts = line.split("\t")
		if len(parts) < 3:
			continue
		user_id = parts[0].strip()
		timestamp_str = parts[1].strip()
		try:
			status_code = int(parts[2].strip())
		except ValueError:
			continue
		records.append(
			{
				"user_id": user_id,
				"timestamp_str": timestamp_str,
				"status_code": status_code,
				"unix_stamp": _to_unix_stamp(timestamp_str),
			}
		)
	return records


def _to_unix_stamp(timestamp_str: str) -> int:
	"""Convert an IST wall-clock string ('YYYY-MM-DD HH:MM:SS') to a UTC Unix timestamp.

	IST is UTC+05:30 (19800 seconds ahead). calendar.timegm treats the tuple as UTC,
	so we subtract the IST offset to arrive at the correct epoch value.
	"""
	try:
		dt = datetime.datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S")
		return calendar.timegm(dt.timetuple()) - 19800
	except ValueError:
		return 0


def _get_last_adms_stamp(sn: str) -> int:
	"""Return the stored last_adms_stamp for the device with serial *sn*, or 0."""
	try:
		settings = frappe.get_single("eSSL Integration Settings")
		for device in settings.devices:
			if device.serial_number == sn:
				return device.last_adms_stamp or 0
	except Exception:
		pass
	return 0


def _update_last_adms_stamp(sn: str, stamp: int) -> None:
	"""Persist *stamp* as last_adms_stamp on the matching device row."""
	try:
		settings = frappe.get_single("eSSL Integration Settings")
		for device in settings.devices:
			if device.serial_number == sn:
				frappe.db.set_value(
					"eSSL Device",
					device.name,
					"last_adms_stamp",
					stamp,
					update_modified=False,
				)
				return
	except Exception:
		frappe.log_error(title="eSSL ADMS Error", message=frappe.get_traceback())
