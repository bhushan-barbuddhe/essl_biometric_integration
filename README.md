# eSSL Biometric Integration

Frappe app that syncs employee attendance punch logs from an **eSSL Web** SOAP server into **Frappe HR** Employee Checkins.

> **Compatibility:** Frappe v15 and v16 · Python ≥ 3.10 · hrms ≥ 15

## How It Works

A scheduler fires **once daily** and enqueues one background job per configured device. Each job calls the eSSL Web `GetTransactionsLog` SOAP endpoint for the period since the last sync, then pushes each punch record directly to Frappe HR via `add_log_based_on_employee_field`. Frappe HR's Auto Attendance determines IN/OUT from the chronological sequence of punches.

## Prerequisites

1. **eSSL Web** software running and its SOAP endpoint (`/WebAPIService.asmx`) reachable from the Frappe server
2. **Frappe HR (hrms)** installed on the **same Frappe site** as this app
3. **Shift Types** configured in Frappe HR with **Auto Attendance** enabled
4. Each **Employee** record must have the **Attendance Device ID** field set to the numeric user ID from eSSL (the first column in the device logs, e.g. `1`, `11`, `138`)

## Installation

```bash
cd /path/to/frappe-bench
bench get-app $URL_OF_THIS_REPO --branch develop
bench --site your-site.local install-app essl_biometric_integration
bench --site your-site.local migrate
```

## Configuration

1. In Frappe Desk, open **eSSL Integration Settings** (search in the top bar)
2. Fill in the following fields:

| Field | Description | Example |
|-------|-------------|---------|
| Base URL | URL to the eSSL Web service directory (without `/WebAPIService.asmx`) | `http://192.168.1.100:81/iclock` |
| Username | eSSL Web login username | `admin` |
| Password | eSSL Web login password | — |

3. In the **Devices** child table, add one row per biometric device:

| Field | Description |
|-------|-------------|
| Device Label | Human-readable name (e.g. `Main Gate`, `Factory Entry`) |
| Serial Number | Device serial number from eSSL Web admin |
| Enabled | Uncheck to pause sync for this device |

> **Last Synced At** is updated automatically after each successful sync — do not edit it manually.

### Manual Sync

Use the **Sync Now** button on the settings page to trigger an immediate sync outside the daily schedule. Any errors are displayed inline in the dialog.

## Finding the Serial Number

In the eSSL Web admin panel:

1. Go to **Device Management → Device List**
2. The **Serial No.** column shows the value to enter in the Devices table

## Monitoring

- Open **Background Jobs** in Frappe Desk to see queued and running sync jobs
- Connection or API errors are logged in **Error Log** (search in Desk) under the title `eSSL Sync Error`

## Troubleshooting

| Symptom | Likely Cause | Fix |
|---------|-------------|-----|
| No jobs appear in Background Jobs | Scheduler not running | Run `bench start` or check `bench doctor` |
| `eSSL Sync Error` with "HTTP 401" or "Invalid credentials" | Wrong eSSL credentials | Update Username / Password in Settings |
| `eSSL Sync Error` with "Failed to reach eSSL server" | Network or firewall issue | Check connectivity from Frappe server to eSSL Web URL |
| `eSSL Sync Error` with "Unable to handle request without a valid action parameter" | Wrong endpoint URL | Ensure Base URL does **not** include `/WebAPIService.asmx` |
| No checkins created despite jobs completing | `Attendance Device ID` not set on employees | Set the field on each Employee to match their eSSL numeric user ID |
| No checkins created despite jobs completing | Frappe HR Auto Attendance not configured | Enable Auto Attendance on Shift Types in Frappe HR |
| `eSSL Sync Error` with wrong serial | Incorrect Serial Number in device row | Copy the exact value from eSSL Web Device Management |

## Architecture Notes

- This app is designed for a **single eSSL Web server**. Multi-server deployments are out of scope.
- **IN/OUT is not determined here** — delegated to Frappe HR's Auto Attendance, which uses the first and last punch of each employee's day.
- The app makes **no HTTP calls to Frappe HR** — it calls `add_log_based_on_employee_field` as a direct Python import, so both apps must be on the same bench site.
- Each device syncs independently via its own RQ job — one device failure does not affect others.
- The **sync window** is `last_synced_at → today`. On the very first sync, it falls back to `yesterday → today`. Frappe HR deduplicates exact `(employee, timestamp)` pairs, so overlap between runs is safe.
- Dates are sent to the eSSL SOAP API in `YYYY-MM-DD` format as required by the `GetTransactionsLog` endpoint.

## Contributing

This app uses `pre-commit` for code formatting and linting. Please [install pre-commit](https://pre-commit.com/#installation) and enable it:

```bash
cd apps/essl_biometric_integration
pre-commit install
```

Pre-commit runs: ruff, eslint, prettier, pyupgrade.

## License

MIT
