import xml.etree.ElementTree as ET

import requests


class EsslConnectionError(Exception):
	pass


class EsslApiError(Exception):
	pass


_SOAP_ENVELOPE = """\
<?xml version="1.0" encoding="utf-8"?>
<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
  <soap:Body>
    <GetTransactionsLog xmlns="http://tempuri.org/">
      <FromDateTime>{from_dt}</FromDateTime>
      <ToDateTime>{to_dt}</ToDateTime>
      <SerialNumber>{serial_number}</SerialNumber>
      <UserName>{username}</UserName>
      <UserPassword>{password}</UserPassword>
      <strDataList></strDataList>
    </GetTransactionsLog>
  </soap:Body>
</soap:Envelope>"""

_HEADERS = {
	"Content-Type": "text/xml; charset=utf-8",
	"SOAPAction": "http://tempuri.org/GetTransactionsLog",
}

_NS = {
	"soap": "http://schemas.xmlsoap.org/soap/envelope/",
	"t": "http://tempuri.org/",
}


def get_transactions(
	base_url: str,
	username: str,
	password: str,
	serial_number: str,
	from_dt: str,
	to_dt: str,
) -> list[dict]:
	"""Fetch punch logs from eSSL Web SOAP API for a given device and date range.

	Returns list of dicts: [{"user_id": str, "timestamp": str}, ...]
	Raises EsslConnectionError on HTTP failure or network error.
	Raises EsslApiError when the API response contains an error message.
	"""
	body = _SOAP_ENVELOPE.format(
		from_dt=from_dt,
		to_dt=to_dt,
		serial_number=serial_number,
		username=username,
		password=password,
	)

	try:
		response = requests.post(
			f"{base_url.rstrip('/')}/WebAPIService.asmx",
			data=body.encode("utf-8"),
			headers=_HEADERS,
			timeout=30,
		)
	except requests.RequestException as exc:
		raise EsslConnectionError(f"Failed to reach eSSL server: {exc}") from exc

	if response.status_code != 200:
		raise EsslConnectionError(
			f"eSSL server returned HTTP {response.status_code}: {response.text[:1000]}"
		)

	root = ET.fromstring(response.text)

	result_el = root.find(".//t:GetTransactionsLogResult", _NS)
	if result_el is not None and result_el.text and "Error" in result_el.text:
		raise EsslApiError(f"eSSL API error: {result_el.text}")

	data_el = root.find(".//t:strDataList", _NS)
	if data_el is None or not data_el.text:
		return []

	logs = []
	for line in data_el.text.splitlines():
		parts = line.split("\t")
		if len(parts) >= 2 and parts[0].strip() and parts[1].strip():
			logs.append({"user_id": parts[0].strip(), "timestamp": parts[1].strip()})

	return logs
