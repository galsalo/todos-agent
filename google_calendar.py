from typing import List, Dict
from datetime import datetime, timedelta
import os
import pytz
import asyncio

def _get_google_account_labels():
    """Get Google account labels from settings, fallback to hardcoded values"""
    try:
        from config_manager import config_manager
        settings = config_manager.load_settings()
        
        # Use new calendar_settings structure if available
        calendar_settings = settings.get("calendar_settings", {})
        if calendar_settings:
            # Convert calendar_settings to the expected format
            google_accounts = {}
            for account_name, account_config in calendar_settings.items():
                included_calendars = account_config.get("included_calendars", [])
                # If no calendars are specified, default to primary
                if not included_calendars:
                    google_accounts[account_name] = ['primary']
                else:
                    google_accounts[account_name] = included_calendars
            
            # Ensure we have at least some default accounts if calendar_settings is empty
            if not google_accounts:
                google_accounts = {
                    'main': ['primary'],
                    'work': ['primary']
                }
            
            return google_accounts
        
        # Fallback to old google_accounts structure for backward compatibility
        return settings.get("google_accounts", {
            'main': ['primary'],
            'work': ['primary']
        })
    except Exception as e:
        print(f"Error loading Google account labels from settings: {e}")
        raise e  # Re-raise the exception instead of returning fallback values

def _get_activity_hours():
    """Get Activity Hours from settings, fallback to hardcoded values"""
    try:
        from config_manager import config_manager
        settings = config_manager.load_settings()
        return settings.get("activity_hours", {})
    except Exception as e:
        print(f"Error loading Activity Hours from settings: {e}")
        raise e  # Re-raise the exception instead of returning fallback values

def _get_timezone():
    """Get timezone from settings, fallback to hardcoded value"""
    try:
        from config_manager import config_manager
        return config_manager.get_timezone()
    except Exception as e:
        print(f"Error loading timezone from settings: {e}")
        raise e  # Re-raise the exception instead of returning fallback value

# Account configuration: maps account labels to their calendar IDs
# Note: This is now loaded dynamically from settings - lazy loading to avoid module init errors
def get_google_account_labels():
    """Get Google account labels from settings"""
    return _get_google_account_labels()

# Activity Hours for different todo lists (24-hour format) 
# Note: This is now loaded dynamically from settings - lazy loading to avoid module init errors
def get_activity_hours():
    """Get Activity Hours from settings"""
    return _get_activity_hours()

def get_todos_list_from_project_id(project_id: str) -> str:
    """Convert project_id to todos_list name using settings from config_manager"""
    try:
        from config_manager import config_manager
        settings = config_manager.load_settings()
        project_mappings = settings.get("project_mappings", {})
        return project_mappings.get(project_id)  # Return None if no mapping found
    except Exception as e:
        print(f"Error loading project mappings from settings: {e}")
        raise e  # Re-raise the exception instead of returning fallback default

# Google Calendar API imports
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

# If modifying these SCOPES, delete the file token.json
SCOPES = ['https://www.googleapis.com/auth/calendar.readonly']

def authenticate_and_save_token(token_filename: str, account_description: str = "Google Account"):
    """Authenticate with Google and save the token to a file."""
    import os
    
    if not os.path.exists('tokens/google_credentials.json'):
        print(f"❌ Missing tokens/google_credentials.json file!")
        print("Setup instructions:")
        print("   1. Go to https://console.cloud.google.com/")
        print("   2. Create a project and enable Google Calendar API")
        print("   3. Go to APIs & Services → Credentials")
        print("   4. Create OAuth 2.0 Client ID (Desktop)")
        print("   5. Download and save as 'tokens/google_credentials.json'")
        raise FileNotFoundError("tokens/google_credentials.json not found. Please set up Google Cloud credentials first.")
    
    # Scopes required for Google Calendar API
    SCOPES = ['https://www.googleapis.com/auth/calendar']
    
    # Create flow from client secrets
    flow = InstalledAppFlow.from_client_secrets_file('tokens/google_credentials.json', SCOPES)
    
    # Run the OAuth flow manually (no browser)
    print(f"🔑 Starting OAuth authentication for {account_description}...")
    print(f"\n" + "="*60)
    print(f"📋 MANUAL AUTHENTICATION REQUIRED")
    print(f"="*60)
    
    # Get the authorization URL
    auth_url, _ = flow.authorization_url(prompt='consent')
    
    print(f"\n1. 🌐 Open this URL in any browser:")
    print(f"   {auth_url}")
    print(f"\n2. 🔑 Complete the authentication process")
    print(f"3. 📋 Copy the authorization code from the browser")
    print(f"4. 📝 Paste it below when prompted")
    print(f"\n" + "="*60)
    
    # Get authorization code from user input
    authorization_code = input("\n📝 Enter the authorization code: ").strip()
    
    # Exchange authorization code for credentials
    flow.fetch_token(code=authorization_code)
    creds = flow.credentials
    
    # Save the credentials
    with open(token_filename, 'w') as token:
        token.write(creds.to_json())
    
    print(f"\n✅ Token saved to {token_filename}")
    print(f"✅ Authentication successful for {account_description}!")
    return creds

def get_creds(token_filename: str):
    """
    Get Google credentials, automatically triggering OAuth flow if tokens are missing.
    """
    # Check if credentials file exists
    if not os.path.exists('tokens/google_credentials.json'):
        print(f"❌ Missing tokens/google_credentials.json file!")
        print(f"📝 To set up Google Calendar integration:")
        print(f"   1. Go to Google Cloud Console (console.cloud.google.com)")
        print(f"   2. Create a project and enable Google Calendar API")
        print(f"   3. Create OAuth 2.0 credentials (Desktop app type)")
        print(f"   4. Download and save as 'tokens/google_credentials.json'")
        raise FileNotFoundError("tokens/google_credentials.json not found. Please set up Google Cloud credentials first.")
    
    # Check if token file exists, if not trigger OAuth flow
    if not os.path.exists(token_filename):
        print(f"🔑 Token file '{token_filename}' not found.")
        print(f"🚀 Starting Google OAuth authentication...")
        
        # Extract account name from token filename for user-friendly prompt
        account_name = token_filename.replace('google_token_', '').replace('.json', '').replace('_', ' ').title()
        if account_name == "Main":
            account_name = "Main Google Account"
        
        try:
            creds = authenticate_and_save_token(token_filename, account_name)
            print(f"✅ OAuth authentication successful for {account_name}!")
            return creds
        except Exception as e:
            print(f"❌ OAuth authentication failed: {e}")
            raise
    
    # Try to load existing token
    try:
        creds = Credentials.from_authorized_user_file(token_filename, SCOPES)
        
        # Check if credentials need refresh
        if not creds.valid:
            if creds.expired and creds.refresh_token:
                print(f"🔄 Refreshing expired token for {token_filename}...")
                creds.refresh(Request())
                # Save refreshed token
                with open(token_filename, 'w') as token:
                    token.write(creds.to_json())
                print(f"✅ Token refreshed successfully!")
            else:
                print(f"🔑 Token invalid, re-authenticating...")
                account_name = token_filename.replace('google_token_', '').replace('.json', '').replace('_', ' ').title()
                creds = authenticate_and_save_token(token_filename, account_name)
                print(f"✅ Re-authentication successful!")
        
        return creds
        
    except Exception as e:
        print(f"❌ Error loading token {token_filename}: {e}")
        print(f"🔑 Starting fresh OAuth authentication...")
        account_name = token_filename.replace('google_token_', '').replace('.json', '').replace('_', ' ').title()
        creds = authenticate_and_save_token(token_filename, account_name)
        print(f"✅ OAuth authentication successful!")
        return creds

def get_available_calendars(token_filename: str) -> List[Dict]:
    """
    Get all available calendars for a given account.
    Returns a list of calendar info dictionaries.
    """
    creds = get_creds(token_filename)
    service = build('calendar', 'v3', credentials=creds)
    calendar_list = service.calendarList().list().execute()
    calendars = calendar_list.get('items', [])
    return [
        {
            'id': cal['id'],
            'summary': cal.get('summary', 'No name'),
            'primary': cal.get('primary', False),
            'selected': cal.get('selected', False),
        }
        for cal in calendars
    ]

async def fetch_schedule_between(start_timestamp: str, end_timestamp: str, token_filename: str = 'google_token_main.json', calendar_ids: List[str] = None) -> List[Dict]:
    """
    Fetch the full Google Calendar schedule between two timestamps for a given account.
    Args:
        start_timestamp (str): The start time in ISO 8601 format (UTC or with timezone).
        end_timestamp (str): The end time in ISO 8601 format (UTC or with timezone).
        token_filename (str): The token file for the account to use.
        calendar_ids (List[str]): List of calendar IDs to fetch from. If None, uses ['primary'].
    Returns:
        List[Dict]: A list of events, each event is a dict with event details.
    """
    if calendar_ids is None:
        calendar_ids = ['primary']
    
    creds = get_creds(token_filename)
    service = build('calendar', 'v3', credentials=creds)
    
    async def fetch_calendar_events(calendar_id: str) -> List[Dict]:
        """Fetch events from a single calendar"""
        try:
            # Create a dedicated function for the API call to avoid lambda issues
            def make_api_call():
                return service.events().list(
                    calendarId=calendar_id,
                    timeMin=start_timestamp,
                    timeMax=end_timestamp,
                    maxResults=2500,
                    singleEvents=True,
                    orderBy='startTime'
                ).execute()
            
            # Run the synchronous API call in a thread pool with timeout
            loop = asyncio.get_event_loop()
            events_result = await asyncio.wait_for(
                loop.run_in_executor(None, make_api_call),
                timeout=30.0  # 30 second timeout
            )
            events = events_result.get('items', [])
            
            # Add calendar info to each event
            for event in events:
                event['calendar_id'] = calendar_id
            
            return events
            
        except asyncio.TimeoutError:
            print(f"Timeout: Could not fetch events from calendar {calendar_id}")
            return []
        except Exception as e:
            print(f"Warning: Could not fetch events from calendar {calendar_id}: {e}")
            return []
    
    try:
        # Fetch from all calendars in parallel with overall timeout
        calendar_tasks = [fetch_calendar_events(calendar_id) for calendar_id in calendar_ids]
        calendar_results = await asyncio.wait_for(
            asyncio.gather(*calendar_tasks, return_exceptions=True),
            timeout=60.0  # 60 second overall timeout
        )
        
        # Flatten the results, handling any exceptions
        all_events = []
        for result in calendar_results:
            if isinstance(result, Exception):
                print(f"Error in calendar fetch: {result}")
                continue
            elif isinstance(result, list):
                all_events.extend(result)
        
    except asyncio.TimeoutError:
        print(f"Overall timeout fetching calendars for {token_filename}")
        return []
    
    # Sort all events by start time
    all_events.sort(key=lambda x: x.get('start', {}).get('dateTime', x.get('start', {}).get('date', '')))
    
    return [
        {
            'id': event.get('id'),
            'summary': event.get('summary'),
            'start': event.get('start'),
            'end': event.get('end'),
            'description': event.get('description'),
            'location': event.get('location'),
            'calendar_id': event.get('calendar_id'),
        }
        for event in all_events
    ]

async def get_free_intervals(start_timestamp: str, end_timestamp: str, account_calendar_mapping: Dict[str, List[str]] = None) -> list:
    # Returns a list of free intervals (dicts with 'start' and 'end') between start and end timestamps, after checking all events in all specified calendars.
    from dateutil.parser import isoparse
    from datetime import datetime, time
    israel_tz = pytz.timezone(_get_timezone())

    def normalize_to_datetime(ts: str, is_start: bool) -> datetime:
        try:
            dt = isoparse(ts)
        except Exception:
            raise ValueError(f"Invalid timestamp: {ts}")
        if dt.tzinfo is None:
            dt = israel_tz.localize(dt)
        else:
            dt = dt.astimezone(israel_tz)
        if len(ts) <= 10:
            if is_start:
                dt = dt.replace(hour=0, minute=0, second=0, microsecond=0)
            else:
                dt = dt.replace(hour=23, minute=59, second=59, microsecond=0)
        return dt

    # Use default mapping if none provided
    if account_calendar_mapping is None:
        account_calendar_mapping = _get_google_account_labels()

    async def fetch_account_events(account_label: str, calendar_ids: List[str]) -> List[tuple]:
        """Fetch events from all calendars for one account"""
        try:
            token_file = f'google_token_{account_label}.json'
            print(f"📅 Fetching calendar events for account: {account_label}")
            events = await fetch_schedule_between(start_timestamp, end_timestamp, token_filename=token_file, calendar_ids=calendar_ids)
            account_busy_intervals = []
            for event in events:
                # Add None checks to prevent TypeError: 'NoneType' object is not subscriptable
                start_obj = event.get('start')
                end_obj = event.get('end')
                
                if start_obj is None or end_obj is None:
                    print(f"⚠️ Skipping event with missing start/end time: {event.get('summary', 'No title')}")
                    continue
                
                start = start_obj.get('dateTime')
                end = end_obj.get('dateTime')
                
                if start and end:
                    start_dt = isoparse(start)
                    if start_dt.tzinfo is None:
                        start_dt = israel_tz.localize(start_dt)
                    else:
                        start_dt = start_dt.astimezone(israel_tz)
                    end_dt = isoparse(end)
                    if end_dt.tzinfo is None:
                        end_dt = israel_tz.localize(end_dt)
                    else:
                        end_dt = end_dt.astimezone(israel_tz)
                    account_busy_intervals.append((start_dt, end_dt))
            print(f"✅ Successfully fetched {len(events)} events for {account_label}")
            return account_busy_intervals
        except FileNotFoundError as e:
            print(f"❌ Google Calendar setup required: {e}")
            print(f"⚠️  Continuing without calendar data for account '{account_label}'")
            return []
        except Exception as e:
            print(f"❌ Error fetching events for account {account_label}: {e}")
            print(f"⚠️  Continuing without calendar data for account '{account_label}'")
            return []
    
    try:
        # Fetch from all accounts in parallel with timeout
        account_tasks = [
            fetch_account_events(account_label, calendar_ids) 
            for account_label, calendar_ids in account_calendar_mapping.items()
        ]
        account_results = await asyncio.wait_for(
            asyncio.gather(*account_tasks, return_exceptions=True),
            timeout=120.0  # 2 minute overall timeout
        )
        
        # Flatten all busy intervals from all accounts
        busy_intervals = []
        for result in account_results:
            if isinstance(result, Exception):
                print(f"Error in account fetch: {result}")
                continue
            elif isinstance(result, list):
                busy_intervals.extend(result)
                
    except asyncio.TimeoutError:
        print("Overall timeout fetching from all accounts")
        busy_intervals = []  # Continue with empty intervals if timeout
    
    interval_start = normalize_to_datetime(start_timestamp, is_start=True)
    interval_end = normalize_to_datetime(end_timestamp, is_start=False)
    busy_intervals.sort()
    merged = []
    for interval in busy_intervals:
        if not merged:
            merged.append(interval)
        else:
            last = merged[-1]
            if interval[0] <= last[1]:
                merged[-1] = (last[0], max(last[1], interval[1]))
            else:
                merged.append(interval)
    free_intervals = []
    current = interval_start
    for busy in merged:
        if busy[0] > current:
            free_intervals.append({'start': current.isoformat(), 'end': busy[0].isoformat()})
        current = max(current, busy[1])
    if current < interval_end:
        free_intervals.append({'start': current.isoformat(), 'end': interval_end.isoformat()})
    return free_intervals

async def get_filtered_free_intervals_for_list(start_timestamp: str, end_timestamp: str, todos_list: str, account_calendar_mapping: Dict[str, List[str]] = None, override_activity_hours: bool = False) -> str:
    """
    Get free intervals filtered by Activity Hours for a specific todo list and format as clean text.
    
    Args:
        start_timestamp (str): Start time in ISO 8601 format
        end_timestamp (str): End time in ISO 8601 format  
        todos_list (str): The todo list name (e.g., 'work', 'personal', 'health', 'learning', etc.)
        account_calendar_mapping (Dict[str, List[str]]): Optional custom mapping of account labels to calendar IDs
        override_activity_hours (bool): If True, skip Activity Hours filtering and allow scheduling at any time
    
    Returns:
        str: Formatted text describing available time slots, filtered by Activity Hours for the specified list
    """
    # Load Activity Hours from configuration file
    from config_manager import config_manager
    try:
        settings = config_manager.load_settings()
        configured_activity_hours = settings.get("activity_hours", {})
    except:
        # Fallback to hardcoded Activity Hours if config loading fails
        configured_activity_hours = _get_activity_hours()
    
    # Use account/calendar mapping from GOOGLE_ACCOUNT_LABELS if none provided
    if account_calendar_mapping is None:
        account_calendar_mapping = _get_google_account_labels()
    
    # Get all free intervals first
    free_intervals = await get_free_intervals(start_timestamp, end_timestamp, account_calendar_mapping)
    
    # Parse dates for timezone handling
    from dateutil.parser import isoparse
    israel_tz = pytz.timezone(_get_timezone())
    current_time = datetime.now(israel_tz)
    
    # Filter out past intervals - only keep future intervals
    future_intervals = []
    for interval in free_intervals:
        start_dt = isoparse(interval['start'])
        end_dt = isoparse(interval['end'])
        
        # Ensure timezone consistency
        if start_dt.tzinfo is None:
            start_dt = israel_tz.localize(start_dt)
        else:
            start_dt = start_dt.astimezone(israel_tz)
            
        if end_dt.tzinfo is None:
            end_dt = israel_tz.localize(end_dt)
        else:
            end_dt = end_dt.astimezone(israel_tz)
        
        # Skip intervals that are entirely in the past
        if end_dt <= current_time:
            continue
            
        # Cut intervals that start in the past to begin from current time
        if start_dt < current_time:
            start_dt = current_time
        
        # Only add intervals that have future time
        if start_dt < end_dt:
            future_intervals.append({
                'start': start_dt.isoformat(),
                'end': end_dt.isoformat()
            })
    
    # Use future intervals instead of all free intervals
    free_intervals = future_intervals
    
    # Check if we should override Activity Hours filtering
    if override_activity_hours:
        # Skip Activity Hours filtering - use all free intervals
        print(f"⚠️  Activity Hours override enabled for '{todos_list}' - scheduling allowed at any time")
        intervals_to_format = free_intervals
        restrictions_note = " (Activity Hours overridden - any hour allowed)"
    # Check if we need to filter by Activity Hours (use configured Activity Hours)
    elif todos_list in configured_activity_hours:
        activity_hours = configured_activity_hours[todos_list]
        
        # Check if any day has Activity Hours enabled (not None)
        has_any_activity_hours = any(
            activity_hours.get(day) is not None 
            for day in ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
        )
        
        # If no Activity Hours are enabled for any day, treat as "any hour"
        if not has_any_activity_hours:
            intervals_to_format = free_intervals
            restrictions_note = " (no Activity Hours enabled - any hour)"
        else:
            # Normal Activity Hours filtering
            filtered_intervals = []
            
            for interval in free_intervals:
                start_dt = isoparse(interval['start'])
                end_dt = isoparse(interval['end'])
                
                # Ensure timezone consistency
                if start_dt.tzinfo is None:
                    start_dt = israel_tz.localize(start_dt)
                else:
                    start_dt = start_dt.astimezone(israel_tz)
                    
                if end_dt.tzinfo is None:
                    end_dt = israel_tz.localize(end_dt)
                else:
                    end_dt = end_dt.astimezone(israel_tz)
                
                # Split interval by days and filter each day
                current_dt = start_dt
                while current_dt < end_dt:
                    # Get the end of current day
                    day_end = current_dt.replace(hour=23, minute=59, second=59, microsecond=999999)
                    interval_end_for_day = min(end_dt, day_end)
                    
                    # Get day of week (lowercase)
                    day_name = current_dt.strftime('%A').lower()
                    
                    # Check if there are Activity Hours for this day
                    if activity_hours.get(day_name) is not None:
                        day_hours = activity_hours[day_name]
                        
                        # Parse Activity Hours for this day
                        work_start_time = datetime.strptime(day_hours['start'], '%H:%M').time()
                        work_end_time = datetime.strptime(day_hours['end'], '%H:%M').time()
                        
                        # Create Activity Hours datetime for this specific day
                        work_start_dt = current_dt.replace(
                            hour=work_start_time.hour, 
                            minute=work_start_time.minute, 
                            second=0, 
                            microsecond=0
                        )
                        work_end_dt = current_dt.replace(
                            hour=work_end_time.hour, 
                            minute=work_end_time.minute, 
                            second=0, 
                            microsecond=0
                        )
                        
                        # Find intersection of free interval and Activity Hours for this day
                        filtered_start = max(current_dt, work_start_dt)
                        filtered_end = min(interval_end_for_day, work_end_dt)
                        
                        # If there's a valid intersection, add it
                        if filtered_start < filtered_end:
                            filtered_intervals.append({
                                'start': filtered_start.isoformat(),
                                'end': filtered_end.isoformat()
                            })
                    
                    # Move to next day
                    current_dt = (current_dt + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
            
            intervals_to_format = filtered_intervals
            restrictions_note = ""
    else:
        # No Activity Hours defined, use all free intervals
        intervals_to_format = free_intervals
        restrictions_note = " (no Activity Hours restrictions)"
    
    # Single formatting section for both cases
    if not intervals_to_format:
        return f"No available time slots found for '{todos_list}' within the specified time range{' and Activity Hours' if todos_list in configured_activity_hours else ''}."
    
    formatted_text = f"Available time slots for '{todos_list}' list{restrictions_note}:\n\n"
    current_day = None
    
    for interval in intervals_to_format:
        start_dt = isoparse(interval['start'])
        end_dt = isoparse(interval['end'])
        
        # Ensure timezone consistency
        if start_dt.tzinfo is None:
            start_dt = israel_tz.localize(start_dt)
        else:
            start_dt = start_dt.astimezone(israel_tz)
            
        if end_dt.tzinfo is None:
            end_dt = israel_tz.localize(end_dt)
        else:
            end_dt = end_dt.astimezone(israel_tz)
        
        day = start_dt.strftime('%A')
        start_time = start_dt.strftime('%H:%M')
        end_time = end_dt.strftime('%H:%M')
        date_str = start_dt.strftime('%Y-%m-%d')
        
        if day != current_day:
            formatted_text += f"**{day}, {date_str}:**\n"
            current_day = day
        
        duration_minutes = int((end_dt - start_dt).total_seconds() / 60)
        formatted_text += f"  • {start_time} - {end_time} ({duration_minutes} minutes)\n"
    
    formatted_text += f"\nTotal available slots: {len(intervals_to_format)}"
    return formatted_text

def get_all_calendar_ids_for_accounts(token_filenames: list) -> Dict[str, List[str]]:
    """
    Get all calendar IDs for all accounts. Useful for discovering available calendars.
    Returns a dict mapping token filename to list of calendar IDs.
    """
    result = {}
    for token_file in token_filenames:
        try:
            calendars = get_available_calendars(token_file)
            result[token_file] = [cal['id'] for cal in calendars if cal.get('selected', True)]
            print(f"\n{token_file}:")
            for cal in calendars:
                selected = "✓" if cal.get('selected', True) else "✗"
                primary = " (PRIMARY)" if cal.get('primary', False) else ""
                print(f"  {selected} {cal['summary']}{primary}")
                print(f"    ID: {cal['id']}")
        except Exception as e:
            print(f"Error getting calendars for {token_file}: {e}")
            result[token_file] = []
    return result

def test_calendar_access(calendar_id: str, token_filenames: list):
    """
    Test which token file can access a specific calendar ID.
    """
    print(f"\n=== Testing access to calendar: {calendar_id} ===")
    for token_file in token_filenames:
        try:
            creds = get_creds(token_file)
            service = build('calendar', 'v3', credentials=creds)
            calendar_info = service.calendars().get(calendarId=calendar_id).execute()
            print(f"✓ {token_file} can access: {calendar_info.get('summary', calendar_id)}")
            return token_file  # Return the working token file
        except Exception as e:
            print(f"✗ {token_file} cannot access this calendar: {e}")
    print(f"No token file can access calendar: {calendar_id}")
    return None

# if __name__ == "__main__":
#     # Authenticate and save tokens for all accounts in GOOGLE_ACCOUNT_LABELS
#     for label in GOOGLE_ACCOUNT_LABELS.keys():
#         token_file = f'google_token_{label}.json'
#         authenticate_and_save_token(token_file, f'Google account for {label}')
#     print("All accounts authenticated. You can now use get_filtered_free_intervals_for_list with these token files.")

#     # Example: Test get_filtered_free_intervals_for_list for different todo lists
#     from datetime import datetime, timedelta
#     israel_tz = pytz.timezone('Asia/Jerusalem')
#     now = datetime.now(israel_tz)
#     start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
#     end_of_day = start_of_day + timedelta(days=7)  # Test for a week
#     start_str = start_of_day.isoformat()
#     end_str = end_of_day.isoformat()

#     # Test with different todo lists using the configured account-calendar mapping
#     test_lists = ["work"]#, "personal", "routines"]
#     for todo_list in test_lists:
#         print(f"\nTesting get_filtered_free_intervals_for_list for '{todo_list}' list:")
#         result = get_filtered_free_intervals_for_list(start_str, end_str, todo_list)
#         print(result)
