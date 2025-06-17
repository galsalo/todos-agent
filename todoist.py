import os
from typing import Optional, List, Dict, Any
import requests
from dotenv import load_dotenv
from datetime import datetime
import pytz

# Load environment variables from .env file
load_dotenv()

TODOIST_API_TOKEN = os.getenv("TODOIST_API_TOKEN")
TODOIST_API_URL = "https://api.todoist.com/rest/v2/tasks"

def get_task_details(task_id: str) -> Dict[str, Any]:
    """
    Get detailed information about a task from Todoist API.
    
    Args:
        task_id (str): The ID of the task to retrieve.
        
    Returns:
        Dict[str, Any]: Task details including project_id, content, priority, etc.
        
    Raises:
        ValueError: If API token is not set
        requests.RequestException: If API call fails
    """
    if not TODOIST_API_TOKEN:
        raise ValueError("TODOIST_API_TOKEN not set in environment variables.")
    
    headers = {
        "Authorization": f"Bearer {TODOIST_API_TOKEN}",
    }
    
    url = f"https://api.todoist.com/rest/v2/tasks/{task_id}"
    response = requests.get(url, headers=headers)
    
    if response.status_code == 200:
        return response.json()
    elif response.status_code == 404:
        raise ValueError(f"Task with ID {task_id} not found")
    else:
        raise requests.RequestException(f"Failed to get task details: {response.status_code} {response.text}")

# This function will later be wrapped as a FunctionTool for use by an AI agent.
def create_todo(
    title: str,
    description: Optional[str] = None,
    start_timestamp: Optional[str] = None,  # ISO 8601 string in Israeli local time (Asia/Jerusalem), e.g. '2025-05-29T13:00:00'
    duration_minutes: Optional[int] = None,
) -> str:
    """
    Create a todo in the Todoist app, scheduled at the given timestamp (Israeli time) and with the specified duration.
    Args:
        title (str): The title of the todo.
        description (Optional[str]): The description of the todo.
        start_timestamp (Optional[str]): The start time in ISO 8601 format (Asia/Jerusalem, e.g. '2025-05-29T13:00:00').
        duration_minutes (Optional[int]): The duration of the todo in minutes.
    Returns:
        str: Confirmation message or created task ID.
    """
    if not TODOIST_API_TOKEN:
        raise ValueError("TODOIST_API_TOKEN not set in environment variables.")

    payload = {
        "content": title,
    }
    if description:
        payload["description"] = description
    if start_timestamp:
        try:
            # Parse as naive datetime (local Israeli time)
            local_dt = datetime.strptime(start_timestamp, "%Y-%m-%dT%H:%M:%S")
        except ValueError:
            raise ValueError("start_timestamp must be in 'YYYY-MM-DDTHH:MM:SS' format, local Israeli time, e.g. '2025-05-29T13:00:00'")
        
        from config_manager import config_manager
        israel_tz = pytz.timezone(config_manager.get_timezone())
        local_dt = israel_tz.localize(local_dt)
        utc_dt = local_dt.astimezone(pytz.utc)
        # Format as RFC3339/ISO 8601 with 'Z' for UTC
        payload["due_datetime"] = utc_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    if duration_minutes:
        payload["duration"] = duration_minutes
        payload["duration_unit"] = "minute"

    headers = {
        "Authorization": f"Bearer {TODOIST_API_TOKEN}",
        "Content-Type": "application/json",
    }

    response = requests.post(TODOIST_API_URL, json=payload, headers=headers)
    if response.status_code in (200, 201):
        return f"Todo '{title}' created successfully."
    else:
        return f"Failed to create todo: {response.status_code} {response.text}"

def update_todo_schedule(
    task_id: str,
    new_start_timestamp: str,  # ISO 8601 string in Israeli local time (Asia/Jerusalem), e.g. '2025-05-29T13:00:00'
    duration_minutes: int,
) -> str:
    """
    Update a todo in Todoist: schedule it at the given timestamp and set its duration.
    Args:
        task_id (str): The ID of the task to update.
        new_start_timestamp (str): The new start time in ISO 8601 format (Asia/Jerusalem, e.g. '2025-05-29T13:00:00').
        duration_minutes (int): The duration of the task in minutes.
    Returns:
        str: Confirmation message or error.
    """
    if not TODOIST_API_TOKEN:
        raise ValueError("TODOIST_API_TOKEN not set in environment variables.")

    try:
        # Parse as naive datetime (local Israeli time)
        local_dt = datetime.strptime(new_start_timestamp, "%Y-%m-%dT%H:%M:%S")
    except ValueError:
        raise ValueError("new_start_timestamp must be in 'YYYY-MM-DDTHH:MM:SS' format, local Israeli time, e.g. '2025-05-29T13:00:00'")
    
    from config_manager import config_manager
    israel_tz = pytz.timezone(config_manager.get_timezone())
    local_dt = israel_tz.localize(local_dt)
    utc_dt = local_dt.astimezone(pytz.utc)
    # Format as RFC3339/ISO 8601 with 'Z' for UTC
    due_datetime = utc_dt.strftime("%Y-%m-%dT%H:%M:%SZ")

    payload = {
        "due_datetime": due_datetime,
        "duration": duration_minutes,
        "duration_unit": "minute",
    }

    headers = {
        "Authorization": f"Bearer {TODOIST_API_TOKEN}",
        "Content-Type": "application/json",
    }

    url = f"https://api.todoist.com/rest/v2/tasks/{task_id}"
    response = requests.post(url, json=payload, headers=headers)
    if response.status_code in (200, 204):
        return f"Todo '{task_id}' updated successfully."
    else:
        return f"Failed to update todo: {response.status_code} {response.text}"

def set_todo_labels(
    task_id: str,
    labels: List[str],
) -> str:
    """
    Set (replace) the labels of a Todoist task by its id.
    Args:
        task_id (str): The ID of the task to update.
        labels (List[str]): The new list of label names to set on the task.
    Returns:
        str: Confirmation message or error.
    """
    if not TODOIST_API_TOKEN:
        raise ValueError("TODOIST_API_TOKEN not set in environment variables.")

    url = f"https://api.todoist.com/rest/v2/tasks/{task_id}"
    payload = {
        "labels": labels
    }
    headers = {
        "Authorization": f"Bearer {TODOIST_API_TOKEN}",
        "Content-Type": "application/json",
    }
    response = requests.post(url, json=payload, headers=headers)
    if response.status_code in (200, 204):
        return f"Labels for task '{task_id}' updated successfully."
    else:
        return f"Failed to update labels: {response.status_code} {response.text}"

def remove_task_scheduling(task_id: str) -> str:
    """
    Remove scheduling from a Todoist task by clearing its due date and duration.
    Args:
        task_id (str): The ID of the task to update.
    Returns:
        str: Confirmation message or error.
    """
    if not TODOIST_API_TOKEN:
        raise ValueError("TODOIST_API_TOKEN not set in environment variables.")

    url = f"https://api.todoist.com/rest/v2/tasks/{task_id}"
    payload = {
        "due_string": "no date",  # This removes the due date
        "duration": None,
        "duration_unit": None
    }
    headers = {
        "Authorization": f"Bearer {TODOIST_API_TOKEN}",
        "Content-Type": "application/json",
    }
    response = requests.post(url, json=payload, headers=headers)
    if response.status_code in (200, 204):
        return f"Scheduling removed from task '{task_id}' successfully."
    else:
        return f"Failed to remove scheduling: {response.status_code} {response.text}"

def get_project_sections(project_id: str) -> List[Dict[str, Any]]:
    """
    Get all sections from a Todoist project.
    
    Args:
        project_id (str): The ID of the project to get sections from.
        
    Returns:
        List[Dict[str, Any]]: List of section objects containing id, name, etc.
        
    Raises:
        ValueError: If API token is not set
        requests.RequestException: If API call fails
    """
    if not TODOIST_API_TOKEN:
        raise ValueError("TODOIST_API_TOKEN not set in environment variables.")
    
    headers = {
        "Authorization": f"Bearer {TODOIST_API_TOKEN}",
    }
    
    url = f"https://api.todoist.com/rest/v2/sections?project_id={project_id}"
    response = requests.get(url, headers=headers)
    
    if response.status_code == 200:
        return response.json()
    else:
        raise requests.RequestException(f"Failed to get project sections: {response.status_code} {response.text}")

def move_task_to_section(task_id: str, section_id: str) -> str:
    """
    Move a task to a specific section in Todoist.
    
    Args:
        task_id (str): The ID of the task to move.
        section_id (str): The ID of the section to move the task to.
        
    Returns:
        str: Confirmation message or error.
    """
    if not TODOIST_API_TOKEN:
        raise ValueError("TODOIST_API_TOKEN not set in environment variables.")
    
    # Validate inputs
    if not task_id or not task_id.strip():
        return "Failed to move task to section: Empty task_id"
    if not section_id or not section_id.strip():
        return "Failed to move task to section: Empty section_id"
    
    # Map numeric section_id to new GUID format if needed
    mapped_section_id = section_id.strip()
    if str(section_id).isdigit():
        try:
            # Use API v1 id_mappings endpoint to convert numeric ID to GUID
            mapping_url = f"https://api.todoist.com/api/v1/id_mappings/sections/{section_id}"
            headers = {"Authorization": f"Bearer {TODOIST_API_TOKEN}"}
            
            mapping_response = requests.get(mapping_url, headers=headers)
            if mapping_response.status_code == 200:
                mapping_list = mapping_response.json()
                for mapping in mapping_list:
                    if mapping.get("old_id") == str(section_id):
                        mapped_section_id = mapping.get("new_id")
                        print(f"Mapped numeric section_id {section_id} -> {mapped_section_id}")
                        break
                else:
                    print(f"Could not map numeric section_id {section_id}, using as is.")
            else:
                print(f"Failed to map section_id {section_id}: {mapping_response.status_code} {mapping_response.text}")
        except Exception as e:
            print(f"Exception mapping section_id {section_id}: {e}")
    
    # Use the dedicated move endpoint from API v1
    url = f"https://api.todoist.com/api/v1/tasks/{task_id.strip()}/move"
    
    # Build payload for the move endpoint
    payload = {
        "section_id": mapped_section_id
    }
    
    headers = {
        "Authorization": f"Bearer {TODOIST_API_TOKEN}",
        "Content-Type": "application/json",
    }
    
    response = requests.post(url, json=payload, headers=headers)
    if response.status_code in (200, 204):
        return f"Task moved to section successfully."
    else:
        return f"Failed to move task to section: {response.status_code} {response.text}"

