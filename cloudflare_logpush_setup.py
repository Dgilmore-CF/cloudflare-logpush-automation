import os
import requests
import json
import sys

# --- Configuration ---
# Load sensitive information from environment variables
API_TOKEN = os.getenv('CLOUDFLARE_API_TOKEN')
DESTINATION_URL = os.getenv('LOGPUSH_ENDPOINT_URL')
# Optional: Authentication for your endpoint (e.g., "Bearer <your_token>")
AUTH_HEADER = os.getenv('LOGPUSH_AUTH_HEADER')

# Dataset Selection
# Defaults to 'http_requests' if not set.
# Valid options for Zones include: http_requests, firewall_events, dns_logs, nel_reports, spectrum_events
# Supports comma-separated values (e.g., "http_requests,firewall_events")
LOGPUSH_DATASETS_RAW = os.getenv('LOGPUSH_DATASET', 'http_requests')

# Cloudflare API base URL
API_BASE_URL = "https://api.cloudflare.com/client/v4"

# List of known valid Zone-level datasets
VALID_ZONE_DATASETS = [
    "http_requests",
    "firewall_events",
    "dns_logs",
    "nel_reports",
    "spectrum_events"
]

# --- End Configuration ---

def get_target_datasets():
    """Parses and cleans the dataset list from environment variable."""
    return [d.strip() for d in LOGPUSH_DATASETS_RAW.split(',') if d.strip()]

def validate_config():
    """Check if the required environment variables are set and valid."""
    if not API_TOKEN:
        print("Error: CLOUDFLARE_API_TOKEN environment variable is not set.", file=sys.stderr)
        return False
    if not DESTINATION_URL:
        print("Error: LOGPUSH_ENDPOINT_URL environment variable is not set.", file=sys.stderr)
        return False
    
    target_datasets = get_target_datasets()
    invalid_datasets = [d for d in target_datasets if d not in VALID_ZONE_DATASETS]
    
    if invalid_datasets:
        print(f"Error: Invalid LOGPUSH_DATASET(s) found: {', '.join(invalid_datasets)}", file=sys.stderr)
        print(f"Valid options are: {', '.join(VALID_ZONE_DATASETS)}", file=sys.stderr)
        return False
    
    print("Configuration loaded successfully.")
    print(f"Destination URL: {DESTINATION_URL}")
    print(f"Datasets to configure: {', '.join(target_datasets)}")
    
    if AUTH_HEADER:
        print("Using Authorization Header for log destination.")
    else:
        print("No Authorization Header provided for log destination.")
    return True

def get_all_zones(headers):
    """
    Fetches all zones from the Cloudflare account, handling pagination.
    """
    all_zones = []
    page = 1
    
    while True:
        try:
            params = {'page': page, 'per_page': 50}
            response = requests.get(
                f"{API_BASE_URL}/zones",
                headers=headers,
                params=params,
                timeout=10
            )
            response.raise_for_status()
            
            data = response.json()
            
            if not data.get('success'):
                print(f"Error listing zones: {data.get('errors')}", file=sys.stderr)
                return []
                
            all_zones.extend(data['result'])
            
            # Check pagination
            result_info = data.get('result_info', {})
            total_pages = result_info.get('total_pages', 1)
            
            if page >= total_pages:
                break  # Exit loop if we've fetched all pages
            
            page += 1
            
        except requests.exceptions.RequestException as e:
            print(f"Error fetching zones (page {page}): {e}", file=sys.stderr)
            return [] # Return empty list on failure
            
    return all_zones

def create_logpush_job(zone_id, zone_name, dataset, headers):
    """
    Creates a Logpush job for a specific zone and dataset.
    """
    endpoint_url = f"{API_BASE_URL}/zones/{zone_id}/logpush/jobs"
    
    # Construct the destination_conf string
    # See: https://developers.cloudflare.com/logs/logpush/logpush-job/api-configuration/
    destination_conf = DESTINATION_URL
    if AUTH_HEADER:
        # Adds the Authorization header as a query parameter for the Logpush service
        # Note: This is how Cloudflare's API configures headers for HTTP destinations.
        # The value must be URL-safe; requests.post will handle encoding the payload.
        # This becomes: "https://.../logs?header_Authorization=Bearer <token>"
        
        # Simple check for existing query params
        separator = '&' if '?' in destination_conf else '?'
        destination_conf += f"{separator}header_Authorization={AUTH_HEADER}"

    job_payload = {
        "name": f"logpush_{dataset}_{zone_name.replace('.', '_')}",
        "destination_conf": destination_conf,
        "dataset": dataset,
        "enabled": True,
        "output_options": {
            "timestamp_format": "rfc3339"
        }
    }
    
    try:
        response = requests.post(
            endpoint_url,
            headers=headers,
            json=job_payload,
            timeout=10
        )
        
        response_data = response.json()
        
        if response.status_code == 200 or response.status_code == 201:
            if response_data.get('success'):
                job_id = response_data.get('result', {}).get('id')
                print(f"  [SUCCESS] Created {dataset} job for {zone_name} (Job ID: {job_id})")
                return True
            else:
                print(f"  [FAILED]  Could not create {dataset} job for {zone_name}. API Error: {response_data.get('errors')}", file=sys.stderr)
                return False
        
        # Handle case where job might already exist
        elif response.status_code == 400:
            errors = response_data.get('errors', [])
            if any(error['code'] == 1007 for error in errors):
                print(f"  [SKIPPED] {dataset} Job for {zone_name} (destination: {DESTINATION_URL}) already exists.")
            else:
                print(f"  [FAILED]  400 Error for {zone_name} ({dataset}). Details: {errors}", file=sys.stderr)
        else:
            print(f"  [FAILED]  Error for {zone_name} - {dataset} (HTTP {response.status_code}): {response.text}", file=sys.stderr)
            
        return False
        
    except requests.exceptions.RequestException as e:
        print(f"  [FAILED]  Request exception for {zone_name} - {dataset}: {e}", file=sys.stderr)
        return False

def get_logpush_jobs(zone_id, headers):
    """
    Retrieves all logpush jobs for a specific zone.
    Returns a list of job objects or empty list on error.
    """
    endpoint_url = f"{API_BASE_URL}/zones/{zone_id}/logpush/jobs"
    
    try:
        response = requests.get(
            endpoint_url,
            headers=headers,
            timeout=10
        )
        response.raise_for_status()
        
        data = response.json()
        
        if data.get('success'):
            return data.get('result', [])
        else:
            print(f"  [ERROR] Failed to retrieve jobs for zone {zone_id}: {data.get('errors')}", file=sys.stderr)
            return []
            
    except requests.exceptions.RequestException as e:
        print(f"  [ERROR] Request exception while fetching jobs for zone {zone_id}: {e}", file=sys.stderr)
        return []

def disable_logpush_job(zone_id, zone_name, job_id, job_name, headers):
    """
    Disables a specific logpush job by setting enabled=false.
    Returns True if successful, False otherwise.
    """
    endpoint_url = f"{API_BASE_URL}/zones/{zone_id}/logpush/jobs/{job_id}"
    
    payload = {
        "enabled": False
    }
    
    try:
        response = requests.put(
            endpoint_url,
            headers=headers,
            json=payload,
            timeout=10
        )
        
        response_data = response.json()
        
        if response.status_code == 200:
            if response_data.get('success'):
                print(f"  [SUCCESS] Disabled job '{job_name}' (ID: {job_id}) for zone {zone_name}")
                return True
            else:
                print(f"  [FAILED]  Could not disable job {job_id} for {zone_name}. API Error: {response_data.get('errors')}", file=sys.stderr)
                return False
        else:
            print(f"  [FAILED]  Error disabling job {job_id} for {zone_name} (HTTP {response.status_code}): {response.text}", file=sys.stderr)
            return False
            
    except requests.exceptions.RequestException as e:
        print(f"  [FAILED]  Request exception while disabling job {job_id} for {zone_name}: {e}", file=sys.stderr)
        return False

def delete_logpush_job(zone_id, zone_name, job_id, job_name, headers):
    """
    Deletes a specific logpush job permanently.
    Returns True if successful, False otherwise.
    """
    endpoint_url = f"{API_BASE_URL}/zones/{zone_id}/logpush/jobs/{job_id}"
    
    try:
        response = requests.delete(
            endpoint_url,
            headers=headers,
            timeout=10
        )
        
        response_data = response.json()
        
        if response.status_code == 200:
            if response_data.get('success'):
                print(f"  [SUCCESS] Deleted job '{job_name}' (ID: {job_id}) for zone {zone_name}")
                return True
            else:
                print(f"  [FAILED]  Could not delete job {job_id} for {zone_name}. API Error: {response_data.get('errors')}", file=sys.stderr)
                return False
        else:
            print(f"  [FAILED]  Error deleting job {job_id} for {zone_name} (HTTP {response.status_code}): {response.text}", file=sys.stderr)
            return False
            
    except requests.exceptions.RequestException as e:
        print(f"  [FAILED]  Request exception while deleting job {job_id} for {zone_name}: {e}", file=sys.stderr)
        return False

def disable_all_logpush_jobs(delete_jobs=False):
    """
    Disables (or optionally deletes) all logpush jobs from all zones 
    accessible by the API token.
    
    Args:
        delete_jobs: If True, permanently deletes jobs instead of just disabling them.
    """
    # Minimal validation - only need API token for this operation
    if not API_TOKEN:
        print("Error: CLOUDFLARE_API_TOKEN environment variable is not set.", file=sys.stderr)
        sys.exit(1)
    
    api_headers = {
        "Authorization": f"Bearer {API_TOKEN}",
        "Content-Type": "application/json"
    }
    
    action_verb = "delete" if delete_jobs else "disable"
    action_verb_present = "Deleting" if delete_jobs else "Disabling"
    
    print(f"\nFetching all zones...")
    zones = get_all_zones(api_headers)
    
    if not zones:
        print("No zones found or API error occurred. Exiting.")
        sys.exit(1)
    
    print(f"Found {len(zones)} zones. {action_verb_present} all logpush jobs...\n")
    
    success_count = 0
    failed_count = 0
    total_jobs = 0
    
    for zone in zones:
        zone_id = zone['id']
        zone_name = zone['name']
        
        print(f"Processing zone: {zone_name} (ID: {zone_id})")
        
        # Get all logpush jobs for this zone
        jobs = get_logpush_jobs(zone_id, api_headers)
        
        if not jobs:
            print(f"  [INFO] No logpush jobs found for {zone_name}")
            continue
        
        print(f"  Found {len(jobs)} logpush job(s)")
        total_jobs += len(jobs)
        
        for job in jobs:
            job_id = job.get('id')
            job_name = job.get('name', 'unnamed')
            job_enabled = job.get('enabled', False)
            
            # Skip if job is already disabled and we're not deleting
            if not delete_jobs and not job_enabled:
                print(f"  [SKIPPED] Job '{job_name}' (ID: {job_id}) is already disabled")
                success_count += 1
                continue
            
            if delete_jobs:
                if delete_logpush_job(zone_id, zone_name, job_id, job_name, api_headers):
                    success_count += 1
                else:
                    failed_count += 1
            else:
                if disable_logpush_job(zone_id, zone_name, job_id, job_name, api_headers):
                    success_count += 1
                else:
                    failed_count += 1
    
    print("\n--- Summary ---")
    print(f"Total logpush jobs found: {total_jobs}")
    print(f"Successfully {action_verb}d: {success_count}")
    print(f"Failed to {action_verb}: {failed_count}")
    print("Script finished.")

def main():
    """
    Main function to run the script.
    """
    if not validate_config():
        sys.exit(1)
        
    api_headers = {
        "Authorization": f"Bearer {API_TOKEN}",
        "Content-Type": "application/json"
    }
    
    print("\nFetching all zones...")
    zones = get_all_zones(api_headers)
    
    if not zones:
        print("No zones found or API error occurred. Exiting.")
        sys.exit(1)
    
    target_datasets = get_target_datasets()
    print(f"Found {len(zones)} zones. Starting Logpush job creation for datasets: {', '.join(target_datasets)}\n")
    
    success_count = 0
    failed_count = 0
    
    for zone in zones:
        zone_id = zone['id']
        zone_name = zone['name']
        
        print(f"Processing zone: {zone_name} (ID: {zone_id})")
        
        for dataset in target_datasets:
            if create_logpush_job(zone_id, zone_name, dataset, api_headers):
                success_count += 1
            else:
                failed_count += 1
            
    print("\n--- Summary ---")
    print(f"Successfully created/skipped: {success_count}")
    print(f"Failed to create: {failed_count}")
    print("Script finished.")

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Cloudflare Logpush Job Management',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Create logpush jobs for all zones
  python cloudflare_logpush_setup.py create
  
  # Disable all logpush jobs (keeps jobs, but stops them)
  python cloudflare_logpush_setup.py disable
  
  # Delete all logpush jobs permanently
  python cloudflare_logpush_setup.py delete
        """
    )
    
    parser.add_argument(
        'action',
        choices=['create', 'disable', 'delete'],
        help='Action to perform: create new jobs, disable existing jobs, or delete existing jobs'
    )
    
    args = parser.parse_args()
    
    if args.action == 'create':
        main()
    elif args.action == 'disable':
        disable_all_logpush_jobs(delete_jobs=False)
    elif args.action == 'delete':
        # Add confirmation for delete
        print("\n⚠️  WARNING: This will PERMANENTLY DELETE all logpush jobs!")
        confirmation = input("Type 'DELETE' to confirm: ")
        if confirmation == 'DELETE':
            disable_all_logpush_jobs(delete_jobs=True)
        else:
            print("Delete operation cancelled.")
            sys.exit(0)
