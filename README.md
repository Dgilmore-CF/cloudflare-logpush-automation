# Cloudflare Logpush Automation

Automates the management of HTTP Endpoint Logpush jobs for all zones accessible by your Cloudflare API token.

## Features

- **Create** logpush jobs for all zones across all accessible accounts
- **Disable** all existing logpush jobs (stops sending logs but keeps configuration)
- **Delete** all logpush jobs permanently
- Supports multiple datasets (http_requests, firewall_events, dns_logs, etc.)
- Automatic pagination for accounts with many zones
- Detailed logging and error handling

## Installation

1. Install requirements:
   ```bash
   pip install requests
   ```

## Configuration

Set the following environment variables:

- `CLOUDFLARE_API_TOKEN` (Required) - Your Cloudflare API token with Logs Edit permissions
- `LOGPUSH_ENDPOINT_URL` (Required for create) - Your HTTP endpoint URL for receiving logs
- `LOGPUSH_AUTH_HEADER` (Optional) - Authorization header value for your endpoint
- `LOGPUSH_DATASET` (Optional) - Comma-separated list of datasets (default: `http_requests`)

Valid datasets: `http_requests`, `firewall_events`, `dns_logs`, `nel_reports`, `spectrum_events`

## Usage

### Create Logpush Jobs

Creates logpush jobs for all zones in all accounts accessible by your API token:

```bash
python cloudflare_logpush_setup.py create
```

### Disable All Logpush Jobs

Disables all logpush jobs (stops sending logs but keeps the job configuration):

```bash
python cloudflare_logpush_setup.py disable
```

### Delete All Logpush Jobs

Permanently deletes all logpush jobs (requires confirmation):

```bash
python cloudflare_logpush_setup.py delete
```

### Help

```bash
python cloudflare_logpush_setup.py --help
```

## Examples

### Create jobs for multiple datasets
```bash
export CLOUDFLARE_API_TOKEN="your_token_here"
export LOGPUSH_ENDPOINT_URL="https://your-endpoint.com/logs"
export LOGPUSH_DATASET="http_requests,firewall_events"
python cloudflare_logpush_setup.py create
```

### With authentication header
```bash
export LOGPUSH_AUTH_HEADER="Bearer your_endpoint_token"
python cloudflare_logpush_setup.py create
```

## Notes

- The script processes all zones accessible by the provided API token
- Jobs are named using the pattern: `logpush_{dataset}_{zone_name}`
- Duplicate job creation is automatically detected and skipped
- All operations include comprehensive error handling and reporting
