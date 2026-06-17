"""
Tests for essl_biometric_integration.adms.receiver

All tests run without a live Frappe site. frappe is mocked at the module
level; hrms is injected into sys.modules via patch.dict so the lazy import
inside handle_log_upload() resolves to the mock.
"""
import sys
import unittest
from unittest.mock import MagicMock, call, patch

# ---------------------------------------------------------------------------
# Bootstrap: inject frappe and hrms stubs before receiver is imported
# ---------------------------------------------------------------------------

_frappe_stub = MagicMock()
_frappe_stub.get_traceback.return_value = ""
_frappe_stub.logger.return_value = MagicMock()

_hrms_module = MagicMock()
_add_log_mock = MagicMock()
_hrms_module.hr.doctype.employee_checkin.employee_checkin.add_log_based_on_employee_field = (
	_add_log_mock
)

_sys_modules_patch = {
	"frappe": _frappe_stub,
	"hrms": _hrms_module,
	"hrms.hr": _hrms_module.hr,
	"hrms.hr.doctype": _hrms_module.hr.doctype,
	"hrms.hr.doctype.employee_checkin": _hrms_module.hr.doctype.employee_checkin,
	"hrms.hr.doctype.employee_checkin.employee_checkin": (
		_hrms_module.hr.doctype.employee_checkin.employee_checkin
	),
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_get_request(sn: str = "SN001") -> MagicMock:
	req = MagicMock()
	req.method = "GET"
	req.args = {"SN": sn}
	return req


def _make_post_request(sn: str = "SN001", body: str = "") -> MagicMock:
	req = MagicMock()
	req.method = "POST"
	req.args = {"SN": sn}
	req.get_data.return_value = body
	return req


def _make_device(sn: str = "SN001", stamp: int = 0, name: str = "dev_001") -> MagicMock:
	d = MagicMock()
	d.serial_number = sn
	d.last_adms_stamp = stamp
	d.name = name
	return d


def _make_settings(*devices) -> MagicMock:
	s = MagicMock()
	s.devices = list(devices)
	return s


_VALID_BODY = (
	"SN=SN001\n"
	"table=ATTLOG\n"
	"Stamp=1718000000\n"
	"138\t2024-06-10 09:00:00\t0\t2\t0\t0\n"
	"138\t2024-06-10 18:00:00\t1\t2\t0\t0\n"
	"11\t2024-06-10 09:05:00\t0\t1\t0\t0\n"
)


# ---------------------------------------------------------------------------
# Tests: handle_heartbeat
# ---------------------------------------------------------------------------


class TestHandleHeartbeat(unittest.TestCase):
	def setUp(self):
		_add_log_mock.reset_mock(side_effect=True)
		_frappe_stub.reset_mock(side_effect=True)
		_frappe_stub.get_traceback.return_value = ""
		_frappe_stub.logger.return_value = MagicMock()

	@patch.dict(sys.modules, _sys_modules_patch)
	def test_heartbeat_known_device(self):
		_frappe_stub.get_single.return_value = _make_settings(_make_device("SN001", stamp=1718000000))

		from essl_biometric_integration.adms.receiver import handle_heartbeat

		result = handle_heartbeat(_make_get_request("SN001"))

		self.assertIn("ATTLOGStamp=1718000000", result)
		self.assertIn("GET OPTION FROM: SN001", result)
		self.assertIn("TimeZone=5.5", result)

	@patch.dict(sys.modules, _sys_modules_patch)
	def test_heartbeat_unknown_device_still_returns_valid_adms_body(self):
		"""An unknown serial number must not 404 or raise — device may be new."""
		_frappe_stub.get_single.return_value = _make_settings()  # no devices

		from essl_biometric_integration.adms.receiver import handle_heartbeat

		result = handle_heartbeat(_make_get_request("UNKNOWN_SN"))

		self.assertIn("GET OPTION FROM: UNKNOWN_SN", result)
		self.assertIn("ATTLOGStamp=0", result)
		self.assertIn("Encrypt=0", result)

	@patch.dict(sys.modules, _sys_modules_patch)
	def test_heartbeat_stamp_zero_on_first_contact(self):
		_frappe_stub.get_single.return_value = _make_settings(_make_device("SN001", stamp=0))

		from essl_biometric_integration.adms.receiver import handle_heartbeat

		result = handle_heartbeat(_make_get_request("SN001"))
		self.assertIn("ATTLOGStamp=0", result)

	@patch.dict(sys.modules, _sys_modules_patch)
	def test_heartbeat_frappe_error_falls_back_to_zero(self):
		_frappe_stub.get_single.side_effect = Exception("DB down")

		from essl_biometric_integration.adms.receiver import handle_heartbeat

		result = handle_heartbeat(_make_get_request("SN001"))
		self.assertIn("ATTLOGStamp=0", result)

		_frappe_stub.get_single.side_effect = None


# ---------------------------------------------------------------------------
# Tests: handle_log_upload
# ---------------------------------------------------------------------------


class TestHandleLogUpload(unittest.TestCase):
	def setUp(self):
		_add_log_mock.reset_mock(side_effect=True)
		_frappe_stub.reset_mock(side_effect=True)
		_frappe_stub.get_traceback.return_value = ""
		_frappe_stub.logger.return_value = MagicMock()
		_frappe_stub.get_single.return_value = _make_settings(_make_device("SN001"))

	@patch.dict(sys.modules, _sys_modules_patch)
	def test_log_upload_returns_ok(self):
		from essl_biometric_integration.adms.receiver import handle_log_upload

		result = handle_log_upload(_make_post_request(body=_VALID_BODY))
		self.assertEqual(result, "OK\n")

	@patch.dict(sys.modules, _sys_modules_patch)
	def test_log_upload_creates_checkins_for_each_valid_record(self):
		from essl_biometric_integration.adms.receiver import handle_log_upload

		handle_log_upload(_make_post_request(body=_VALID_BODY))

		self.assertEqual(_add_log_mock.call_count, 3)

	@patch.dict(sys.modules, _sys_modules_patch)
	def test_log_upload_status_mapping_in(self):
		body = "138\t2024-06-10 09:00:00\t0\t2\t0\t0\n"
		from essl_biometric_integration.adms.receiver import handle_log_upload

		handle_log_upload(_make_post_request(body=body))

		_add_log_mock.assert_called_once()
		kwargs = _add_log_mock.call_args.kwargs
		self.assertEqual(kwargs["log_type"], "IN")

	@patch.dict(sys.modules, _sys_modules_patch)
	def test_log_upload_status_mapping_out(self):
		body = "138\t2024-06-10 18:00:00\t1\t2\t0\t0\n"
		from essl_biometric_integration.adms.receiver import handle_log_upload

		_add_log_mock.reset_mock()
		handle_log_upload(_make_post_request(body=body))

		kwargs = _add_log_mock.call_args.kwargs
		self.assertEqual(kwargs["log_type"], "OUT")

	@patch.dict(sys.modules, _sys_modules_patch)
	def test_log_upload_status_mapping_ot_in(self):
		body = "138\t2024-06-10 20:00:00\t4\t2\t0\t0\n"
		from essl_biometric_integration.adms.receiver import handle_log_upload

		_add_log_mock.reset_mock()
		handle_log_upload(_make_post_request(body=body))

		kwargs = _add_log_mock.call_args.kwargs
		self.assertEqual(kwargs["log_type"], "IN")

	@patch.dict(sys.modules, _sys_modules_patch)
	def test_log_upload_status_mapping_ot_out(self):
		body = "138\t2024-06-10 22:00:00\t5\t2\t0\t0\n"
		from essl_biometric_integration.adms.receiver import handle_log_upload

		_add_log_mock.reset_mock()
		handle_log_upload(_make_post_request(body=body))

		kwargs = _add_log_mock.call_args.kwargs
		self.assertEqual(kwargs["log_type"], "OUT")

	@patch.dict(sys.modules, _sys_modules_patch)
	def test_log_upload_status_2_is_skipped(self):
		"""Status code 2 (card) is not mapped — the record must be silently skipped."""
		body = "138\t2024-06-10 09:00:00\t2\t0\t0\t0\n"
		from essl_biometric_integration.adms.receiver import handle_log_upload

		_add_log_mock.reset_mock()
		result = handle_log_upload(_make_post_request(body=body))

		_add_log_mock.assert_not_called()
		self.assertEqual(result, "OK\n")

	@patch.dict(sys.modules, _sys_modules_patch)
	def test_log_upload_skips_unmapped_employee_and_continues(self):
		"""One record with an unknown user_id must not block processing of the rest."""
		_add_log_mock.reset_mock()
		_add_log_mock.side_effect = [Exception("No Employee found"), None, None]

		body = (
			"999\t2024-06-10 09:00:00\t0\t2\t0\t0\n"
			"138\t2024-06-10 09:00:00\t0\t2\t0\t0\n"
			"11\t2024-06-10 09:05:00\t0\t2\t0\t0\n"
		)
		from essl_biometric_integration.adms.receiver import handle_log_upload

		result = handle_log_upload(_make_post_request(body=body))

		self.assertEqual(_add_log_mock.call_count, 3)
		self.assertEqual(result, "OK\n")

		_add_log_mock.side_effect = None

	@patch.dict(sys.modules, _sys_modules_patch)
	def test_log_upload_updates_last_adms_stamp(self):
		from essl_biometric_integration.adms.receiver import handle_log_upload

		handle_log_upload(_make_post_request(body=_VALID_BODY))

		# frappe.db.set_value must have been called to persist the stamp
		_frappe_stub.db.set_value.assert_called_once()
		call_args = _frappe_stub.db.set_value.call_args
		self.assertEqual(call_args.args[0], "eSSL Device")
		self.assertEqual(call_args.args[2], "last_adms_stamp")
		# Stamp must be a positive integer
		self.assertGreater(call_args.args[3], 0)

	@patch.dict(sys.modules, _sys_modules_patch)
	def test_malformed_body_does_not_crash(self):
		"""Garbage POST body must return OK and not raise an unhandled exception."""
		garbage = "not\x00valid\ndata\n\xff\xfe\nSN=oops"
		from essl_biometric_integration.adms.receiver import handle_log_upload

		result = handle_log_upload(_make_post_request(body=garbage))
		self.assertEqual(result, "OK\n")

	@patch.dict(sys.modules, _sys_modules_patch)
	def test_empty_body_does_not_crash(self):
		from essl_biometric_integration.adms.receiver import handle_log_upload

		result = handle_log_upload(_make_post_request(body=""))
		self.assertEqual(result, "OK\n")
		_add_log_mock.assert_not_called()

	@patch.dict(sys.modules, _sys_modules_patch)
	def test_header_lines_are_not_treated_as_records(self):
		"""Lines like SN=..., table=..., Stamp=... must not produce checkins."""
		body = "SN=SN001\ntable=ATTLOG\nStamp=1718000000\n"
		from essl_biometric_integration.adms.receiver import handle_log_upload

		_add_log_mock.reset_mock()
		handle_log_upload(_make_post_request(body=body))
		_add_log_mock.assert_not_called()


# ---------------------------------------------------------------------------
# Tests: handle (top-level dispatcher)
# ---------------------------------------------------------------------------


class TestHandle(unittest.TestCase):
	def setUp(self):
		_add_log_mock.reset_mock(side_effect=True)
		# reset_mock(side_effect=True) propagates to all child mocks, clearing any
		# side_effect left by previous tests so stale exceptions don't leak.
		_frappe_stub.reset_mock(side_effect=True)
		_frappe_stub.get_traceback.return_value = ""
		_frappe_stub.logger.return_value = MagicMock()

	@patch.dict(sys.modules, _sys_modules_patch)
	def test_get_dispatches_to_heartbeat(self):
		_frappe_stub.get_single.return_value = _make_settings(_make_device("SN001", stamp=42))
		mock_request = _make_get_request("SN001")
		_frappe_stub.local.request = mock_request

		from essl_biometric_integration.adms.receiver import handle

		response = handle()
		self.assertEqual(response.content_type, "text/plain; charset=utf-8")
		self.assertIn(b"ATTLOGStamp=42", response.data)

	@patch.dict(sys.modules, _sys_modules_patch)
	def test_post_dispatches_to_log_upload(self):
		_frappe_stub.get_single.return_value = _make_settings(_make_device("SN001"))
		mock_request = _make_post_request(body=_VALID_BODY)
		_frappe_stub.local.request = mock_request

		from essl_biometric_integration.adms.receiver import handle

		response = handle()
		self.assertEqual(response.data, b"OK\n")
		self.assertEqual(response.content_type, "text/plain; charset=utf-8")

	@patch.dict(sys.modules, _sys_modules_patch)
	def test_exception_in_handler_returns_200_not_500(self):
		"""Device must never receive a 5xx — log silently and return 200.

		The exception is patched at handle_heartbeat level because _get_last_adms_stamp
		deliberately catches internal errors so the device always gets a valid response.
		We test the outer guard in handle() by making handle_heartbeat itself raise.
		"""
		mock_request = _make_get_request("SN001")
		_frappe_stub.local.request = mock_request

		from essl_biometric_integration.adms import receiver

		with patch.object(receiver, "handle_heartbeat", side_effect=RuntimeError("crash")):
			response = receiver.handle()

		self.assertEqual(response.status_code, 200)
		_frappe_stub.log_error.assert_called_once()


# ---------------------------------------------------------------------------
# Tests: _parse_attlog_body
# ---------------------------------------------------------------------------


class TestParseAttlogBody(unittest.TestCase):
	@patch.dict(sys.modules, _sys_modules_patch)
	def test_parses_valid_lines(self):
		from essl_biometric_integration.adms.receiver import _parse_attlog_body

		body = "138\t2024-06-10 09:00:00\t0\t2\t0\t0\n11\t2024-06-10 18:00:00\t1\t2\t0\t0\n"
		records = _parse_attlog_body(body)
		self.assertEqual(len(records), 2)
		self.assertEqual(records[0]["user_id"], "138")
		self.assertEqual(records[0]["timestamp_str"], "2024-06-10 09:00:00")
		self.assertEqual(records[0]["status_code"], 0)
		self.assertEqual(records[1]["status_code"], 1)

	@patch.dict(sys.modules, _sys_modules_patch)
	def test_skips_header_lines(self):
		from essl_biometric_integration.adms.receiver import _parse_attlog_body

		body = "SN=SN001\ntable=ATTLOG\nStamp=1718000000\n138\t2024-06-10 09:00:00\t0\t2\t0\t0\n"
		records = _parse_attlog_body(body)
		self.assertEqual(len(records), 1)

	@patch.dict(sys.modules, _sys_modules_patch)
	def test_returns_empty_list_for_garbage(self):
		from essl_biometric_integration.adms.receiver import _parse_attlog_body

		records = _parse_attlog_body("garbage\x00data\n!!!\n")
		self.assertEqual(records, [])

	@patch.dict(sys.modules, _sys_modules_patch)
	def test_unix_stamp_is_populated(self):
		from essl_biometric_integration.adms.receiver import _parse_attlog_body

		body = "138\t2024-06-10 09:00:00\t0\t2\t0\t0\n"
		records = _parse_attlog_body(body)
		self.assertGreater(records[0]["unix_stamp"], 0)


if __name__ == "__main__":
	unittest.main()
