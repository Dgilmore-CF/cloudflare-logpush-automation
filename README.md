# Cloudflare Logpush Automation

Automates the creation of HTTP Endpoint Logpush jobs for all zones in a Cloudflare account.

## Usage

1. Install requirements:
   `pip install requests`

2. Set Environment Variables:
   - `CLOUDFLARE_API_TOKEN`
   - `LOGPUSH_ENDPOINT_URL`
   - `LOGPUSH_DATASET` (Optional, defaults to http_requests)

3. Run the script:
   `python cloudflare_logpush_setup.py`
