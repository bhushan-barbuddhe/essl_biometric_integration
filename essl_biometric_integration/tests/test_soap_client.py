import unittest
from unittest.mock import MagicMock, patch

SAMPLE_RESPONSE = """<?xml version="1.0" encoding="utf-8"?>
<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"
               xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
               xmlns:xsd="http://www.w3.org/2001/XMLSchema">
    <soap:Body>
        <GetTransactionsLogResponse xmlns="http://tempuri.org/">
            <GetTransactionsLogResult>Logs Count:3</GetTransactionsLogResult>
            <strDataList>1\t2026-05-16 11:10:01\t
11\t2026-05-16 09:39:15\t
138\t2026-05-18 09:02:33\t
</strDataList>
        </GetTransactionsLogResponse>
    </soap:Body>
</soap:Envelope>"""

ERROR_RESPONSE = """<?xml version="1.0" encoding="utf-8"?>
<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"
               xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
               xmlns:xsd="http://www.w3.org/2001/XMLSchema">
    <soap:Body>
        <GetTransactionsLogResponse xmlns="http://tempuri.org/">
            <GetTransactionsLogResult>Error: Invalid credentials</GetTransactionsLogResult>
            <strDataList></strDataList>
        </GetTransactionsLogResponse>
    </soap:Body>
</soap:Envelope>"""

EMPTY_RESPONSE = """<?xml version="1.0" encoding="utf-8"?>
<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"
               xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
               xmlns:xsd="http://www.w3.org/2001/XMLSchema">
    <soap:Body>
        <GetTransactionsLogResponse xmlns="http://tempuri.org/">
            <GetTransactionsLogResult>Logs Count:0</GetTransactionsLogResult>
            <strDataList></strDataList>
        </GetTransactionsLogResponse>
    </soap:Body>
</soap:Envelope>"""

BLANKS_RESPONSE = """<?xml version="1.0" encoding="utf-8"?>
<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"
               xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
               xmlns:xsd="http://www.w3.org/2001/XMLSchema">
    <soap:Body>
        <GetTransactionsLogResponse xmlns="http://tempuri.org/">
            <GetTransactionsLogResult>Logs Count:2</GetTransactionsLogResult>
            <strDataList>1\t2026-05-16 11:10:01\t

\t\t
138\t2026-05-18 09:02:33\t
</strDataList>
        </GetTransactionsLogResponse>
    </soap:Body>
</soap:Envelope>"""


def _mock_http(status_code=200, text=""):
	mock = MagicMock()
	mock.status_code = status_code
	mock.text = text
	return mock


class TestGetTransactions(unittest.TestCase):
	def _call(self, **kwargs):
		from essl_biometric_integration.utils.soap_client import get_transactions
		defaults = dict(
			base_url="http://192.168.1.100/ESSLService",
			username="admin",
			password="secret",
			serial_number="SN001",
			from_dt="2026-05-16 00:00:00",
			to_dt="2026-05-16 23:59:59",
		)
		defaults.update(kwargs)
		return get_transactions(**defaults)

	@patch("essl_biometric_integration.utils.soap_client.requests.post")
	def test_parses_tab_delimited_response(self, mock_post):
		mock_post.return_value = _mock_http(200, SAMPLE_RESPONSE)
		logs = self._call()
		self.assertEqual(len(logs), 3)
		self.assertEqual(logs[0], {"user_id": "1", "timestamp": "2026-05-16 11:10:01"})
		self.assertEqual(logs[1], {"user_id": "11", "timestamp": "2026-05-16 09:39:15"})
		self.assertEqual(logs[2], {"user_id": "138", "timestamp": "2026-05-18 09:02:33"})

	@patch("essl_biometric_integration.utils.soap_client.requests.post")
	def test_raises_connection_error_on_non_200(self, mock_post):
		from essl_biometric_integration.utils.soap_client import EsslConnectionError
		mock_post.return_value = _mock_http(500, "Internal Server Error")
		with self.assertRaises(EsslConnectionError):
			self._call()

	@patch("essl_biometric_integration.utils.soap_client.requests.post")
	def test_raises_api_error_when_result_contains_error(self, mock_post):
		from essl_biometric_integration.utils.soap_client import EsslApiError
		mock_post.return_value = _mock_http(200, ERROR_RESPONSE)
		with self.assertRaises(EsslApiError):
			self._call()

	@patch("essl_biometric_integration.utils.soap_client.requests.post")
	def test_returns_empty_list_for_empty_data(self, mock_post):
		mock_post.return_value = _mock_http(200, EMPTY_RESPONSE)
		self.assertEqual(self._call(), [])

	@patch("essl_biometric_integration.utils.soap_client.requests.post")
	def test_skips_blank_and_incomplete_lines(self, mock_post):
		mock_post.return_value = _mock_http(200, BLANKS_RESPONSE)
		logs = self._call()
		self.assertEqual(len(logs), 2)
		user_ids = [l["user_id"] for l in logs]
		self.assertNotIn("", user_ids)

	@patch("essl_biometric_integration.utils.soap_client.requests.post")
	def test_raises_connection_error_on_request_exception(self, mock_post):
		import requests as req
		from essl_biometric_integration.utils.soap_client import EsslConnectionError
		mock_post.side_effect = req.RequestException("connection timeout")
		with self.assertRaises(EsslConnectionError):
			self._call()

	@patch("essl_biometric_integration.utils.soap_client.requests.post")
	def test_posts_correct_soap_envelope(self, mock_post):
		mock_post.return_value = _mock_http(200, EMPTY_RESPONSE)
		self._call(serial_number="DEV-42", from_dt="2026-05-01 00:00:00", to_dt="2026-05-31 23:59:59")
		_, kwargs = mock_post.call_args
		body = kwargs.get("data", b"").decode("utf-8")
		self.assertIn("<SerialNumber>DEV-42</SerialNumber>", body)
		self.assertIn("<FromDateTime>2026-05-01 00:00:00</FromDateTime>", body)
		self.assertIn("<ToDateTime>2026-05-31 23:59:59</ToDateTime>", body)
		self.assertEqual(kwargs["headers"]["SOAPAction"], "http://tempuri.org/GetTransactionsLog")


if __name__ == "__main__":
	unittest.main()
