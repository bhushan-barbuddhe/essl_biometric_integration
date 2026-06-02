import unittest
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch


def _make_device(enabled=True, serial="SN001", name="dev_abc", last_synced_at=None):
	d = MagicMock()
	d.enabled = enabled
	d.serial_number = serial
	d.name = name
	d.last_synced_at = last_synced_at
	return d


def _make_settings(base_url="http://192.168.1.100/ESSLService", username="admin", devices=None):
	s = MagicMock()
	s.base_url = base_url
	s.username = username
	s.devices = devices or []
	s.get_password.return_value = "secret"
	return s


NOW = datetime(2026, 6, 2, 10, 0, 0)


class TestEnqueueSyncAllDevices(unittest.TestCase):
	@patch("essl_biometric_integration.utils.sync.now_datetime", return_value=NOW)
	@patch("essl_biometric_integration.utils.sync.frappe")
	def test_enqueues_overdue_device(self, mock_frappe, _now):
		device = _make_device(last_synced_at=NOW - timedelta(minutes=35))
		mock_frappe.get_single.return_value = _make_settings(devices=[device])

		from essl_biometric_integration.utils.sync import enqueue_sync_all_devices
		enqueue_sync_all_devices()

		mock_frappe.enqueue.assert_called_once_with(
			"essl_biometric_integration.utils.sync.sync_device",
			device_name="dev_abc",
			queue="long",
			timeout=600,
		)

	@patch("essl_biometric_integration.utils.sync.now_datetime", return_value=NOW)
	@patch("essl_biometric_integration.utils.sync.frappe")
	def test_enqueues_device_with_no_previous_sync(self, mock_frappe, _now):
		device = _make_device(last_synced_at=None)
		mock_frappe.get_single.return_value = _make_settings(devices=[device])

		from essl_biometric_integration.utils.sync import enqueue_sync_all_devices
		enqueue_sync_all_devices()

		mock_frappe.enqueue.assert_called_once()

	@patch("essl_biometric_integration.utils.sync.now_datetime", return_value=NOW)
	@patch("essl_biometric_integration.utils.sync.frappe")
	def test_skips_device_not_yet_due(self, mock_frappe, _now):
		device = _make_device(last_synced_at=NOW - timedelta(minutes=10))
		mock_frappe.get_single.return_value = _make_settings(devices=[device])

		from essl_biometric_integration.utils.sync import enqueue_sync_all_devices
		enqueue_sync_all_devices()

		mock_frappe.enqueue.assert_not_called()

	@patch("essl_biometric_integration.utils.sync.now_datetime", return_value=NOW)
	@patch("essl_biometric_integration.utils.sync.frappe")
	def test_skips_disabled_device(self, mock_frappe, _now):
		device = _make_device(enabled=False)
		mock_frappe.get_single.return_value = _make_settings(devices=[device])

		from essl_biometric_integration.utils.sync import enqueue_sync_all_devices
		enqueue_sync_all_devices()

		mock_frappe.enqueue.assert_not_called()

	@patch("essl_biometric_integration.utils.sync.now_datetime", return_value=NOW)
	@patch("essl_biometric_integration.utils.sync.frappe")
	def test_returns_early_if_base_url_missing(self, mock_frappe, _now):
		mock_frappe.get_single.return_value = _make_settings(base_url="", devices=[_make_device()])

		from essl_biometric_integration.utils.sync import enqueue_sync_all_devices
		enqueue_sync_all_devices()

		mock_frappe.enqueue.assert_not_called()

	@patch("essl_biometric_integration.utils.sync.now_datetime", return_value=NOW)
	@patch("essl_biometric_integration.utils.sync.frappe")
	def test_enqueues_multiple_due_devices(self, mock_frappe, _now):
		d1 = _make_device(name="d1", last_synced_at=NOW - timedelta(minutes=40))
		d2 = _make_device(name="d2", last_synced_at=NOW - timedelta(minutes=5))
		d3 = _make_device(name="d3", last_synced_at=None)
		mock_frappe.get_single.return_value = _make_settings(devices=[d1, d2, d3])

		from essl_biometric_integration.utils.sync import enqueue_sync_all_devices
		enqueue_sync_all_devices()

		self.assertEqual(mock_frappe.enqueue.call_count, 2)
		enqueued_names = [c.kwargs["device_name"] for c in mock_frappe.enqueue.call_args_list]
		self.assertIn("d1", enqueued_names)
		self.assertIn("d3", enqueued_names)
		self.assertNotIn("d2", enqueued_names)


class TestSyncDevice(unittest.TestCase):
	@patch("essl_biometric_integration.utils.sync.now_datetime", return_value=NOW)
	@patch("essl_biometric_integration.utils.sync.frappe")
	def test_pushes_logs_and_updates_last_synced_at(self, mock_frappe, _now):
		mock_frappe.ValidationError = Exception
		mock_frappe.get_single.return_value = _make_settings()
		mock_frappe.get_doc.return_value = _make_device(last_synced_at=NOW - timedelta(minutes=35))

		mock_push = MagicMock()
		mock_get_tx = MagicMock(return_value=[
			{"user_id": "1", "timestamp": "2026-06-02 09:00:00"},
			{"user_id": "138", "timestamp": "2026-06-02 09:15:00"},
		])

		with patch("essl_biometric_integration.utils.sync.get_transactions", mock_get_tx), \
		     patch("essl_biometric_integration.utils.sync._push_checkin", mock_push):
			from essl_biometric_integration.utils.sync import sync_device
			sync_device("dev_abc")

		self.assertEqual(mock_push.call_count, 2)
		mock_frappe.get_doc.return_value.db_set.assert_called_once_with("last_synced_at", NOW)

	@patch("essl_biometric_integration.utils.sync.now_datetime", return_value=NOW)
	@patch("essl_biometric_integration.utils.sync.frappe")
	def test_skips_unmatched_employee_and_continues(self, mock_frappe, _now):
		mock_frappe.ValidationError = Exception
		mock_frappe.get_single.return_value = _make_settings()
		device = _make_device(last_synced_at=None)
		mock_frappe.get_doc.return_value = device

		mock_push = MagicMock(side_effect=[Exception("No Employee found"), None])
		mock_get_tx = MagicMock(return_value=[
			{"user_id": "999", "timestamp": "2026-06-02 09:00:00"},
			{"user_id": "1", "timestamp": "2026-06-02 09:10:00"},
		])

		with patch("essl_biometric_integration.utils.sync.get_transactions", mock_get_tx), \
		     patch("essl_biometric_integration.utils.sync._push_checkin", mock_push):
			from essl_biometric_integration.utils.sync import sync_device
			sync_device("dev_abc")

		self.assertEqual(mock_push.call_count, 2)
		device.db_set.assert_called_once_with("last_synced_at", NOW)

	@patch("essl_biometric_integration.utils.sync.now_datetime", return_value=NOW)
	@patch("essl_biometric_integration.utils.sync.frappe")
	def test_does_not_update_last_synced_at_on_soap_failure(self, mock_frappe, _now):
		mock_frappe.ValidationError = Exception
		mock_frappe.get_single.return_value = _make_settings()
		device = _make_device(last_synced_at=None)
		mock_frappe.get_doc.return_value = device

		from essl_biometric_integration.utils.soap_client import EsslConnectionError
		mock_get_tx = MagicMock(side_effect=EsslConnectionError("timeout"))

		with patch("essl_biometric_integration.utils.sync.get_transactions", mock_get_tx):
			from essl_biometric_integration.utils.sync import sync_device
			with self.assertRaises(EsslConnectionError):
				sync_device("dev_abc")

		device.db_set.assert_not_called()

	@patch("essl_biometric_integration.utils.sync.now_datetime", return_value=NOW)
	@patch("essl_biometric_integration.utils.sync.frappe")
	def test_uses_last_synced_at_as_from_dt(self, mock_frappe, _now):
		mock_frappe.ValidationError = Exception
		mock_frappe.get_single.return_value = _make_settings()
		last_sync = NOW - timedelta(minutes=35)
		mock_frappe.get_doc.return_value = _make_device(last_synced_at=last_sync)

		mock_get_tx = MagicMock(return_value=[])

		with patch("essl_biometric_integration.utils.sync.get_transactions", mock_get_tx), \
		     patch("essl_biometric_integration.utils.sync._push_checkin", MagicMock()):
			from essl_biometric_integration.utils.sync import sync_device
			sync_device("dev_abc")

		call_kwargs = mock_get_tx.call_args.kwargs
		self.assertEqual(call_kwargs["from_dt"], last_sync.strftime("%Y-%m-%d"))
		self.assertEqual(call_kwargs["to_dt"], NOW.strftime("%Y-%m-%d"))

	@patch("essl_biometric_integration.utils.sync.now_datetime", return_value=NOW)
	@patch("essl_biometric_integration.utils.sync.frappe")
	def test_uses_now_minus_interval_as_from_dt_on_first_run(self, mock_frappe, _now):
		mock_frappe.ValidationError = Exception
		mock_frappe.get_single.return_value = _make_settings()
		mock_frappe.get_doc.return_value = _make_device(last_synced_at=None)

		mock_get_tx = MagicMock(return_value=[])

		with patch("essl_biometric_integration.utils.sync.get_transactions", mock_get_tx), \
		     patch("essl_biometric_integration.utils.sync._push_checkin", MagicMock()):
			from essl_biometric_integration.utils.sync import sync_device
			sync_device("dev_abc")

		expected_from = (NOW - timedelta(days=1)).strftime("%Y-%m-%d")
		self.assertEqual(mock_get_tx.call_args.kwargs["from_dt"], expected_from)


if __name__ == "__main__":
	unittest.main()
