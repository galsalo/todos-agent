import asyncio
from autogen_agentchat.agents import AssistantAgent
from autogen_agentchat.conditions import FunctionCallTermination
from autogen_agentchat.teams import RoundRobinGroupChat
from autogen_ext.models.openai import OpenAIChatCompletionClient
from google_calendar import get_filtered_free_intervals_for_list, get_todos_list_from_project_id
from todoist import create_todo, update_todo_schedule, set_todo_labels, get_task_details
from datetime import datetime, timedelta
import pytz
from typing import List, Dict, Optional, Any
from dotenv import load_dotenv
from config_manager import config_manager

# Load environment variables from .env file
load_dotenv()

# Load configuration
config_manager

# Global context for current task processing
_current_task_context = {
    "todos_list": None,
    "task_labels": None
}

def has_override_activity_hours_label(labels: List[str]) -> bool:
    """
    Check if a task has the 'Override Activity Hours' label.
    
    Args:
        labels: List of task labels
        
    Returns:
        bool: True if task has 'Override Activity Hours' label, False otherwise
    """
    if not labels:
        return False
    
    # Check for various forms of the override activity hours label
    override_variants = [
        'Override Activity Hours',
        'override activity hours', 
        'Override activity hours',
        'override_activity_hours',
        'OverrideActivityHours'
    ]
    
    return any(label in override_variants for label in labels)

# Define the tools for the agent
async def get_free_intervals_tool(days_ahead: int) -> str:
    """
    Get available time slots for scheduling tasks for the next few days.
    Uses the todo list from the current task context automatically.
    Args:
        days_ahead (int): Number of days from now to check (e.g., 3 for the next 3 days).
    Returns:
        str: Formatted text showing available time slots appropriate for the current task's todo list type.
    """
    # Get todos_list from current context
    todos_list = _current_task_context.get("todos_list")
    if not todos_list:
        raise ValueError("No todos_list found in current task context. This should not happen during normal operation.")
    
    # Get task labels from current context
    task_labels = _current_task_context.get("task_labels", [])
    
    # Check if task has Override Activity Hours label
    override_activity_hours = has_override_activity_hours_label(task_labels)
    
    if override_activity_hours:
        print(f"🔓 Task has 'Override Activity Hours' label - bypassing Activity Hours restrictions")
    
    # Calculate start and end timestamps
    try:
        israel_tz = pytz.timezone(config_manager.get_timezone())
    except Exception as e:
        print(f"❌ Error loading timezone in get_free_intervals_tool: {e}")
        # Fallback to default timezone
        israel_tz = pytz.timezone("Asia/Jerusalem")
    
    now = datetime.now(israel_tz)
    start_timestamp = now.replace(microsecond=0).isoformat()
    end_timestamp = (now + timedelta(days=days_ahead)).replace(microsecond=0).isoformat()
    
    return await get_filtered_free_intervals_for_list(start_timestamp, end_timestamp, todos_list, override_activity_hours=override_activity_hours)

async def get_free_intervals_for_date_tool(target_date: str) -> str:
    """
    Get available time slots for a specific date.
    
    Args:
        target_date (str): The target date in YYYY-MM-DD format.
                          Examples: "2024-01-15", "2024-12-25", "2025-03-10"
    
    Returns:
        str: Formatted text showing available time slots for the specified date
    """
    # Get todos_list from current context
    todos_list = _current_task_context.get("todos_list")
    if not todos_list:
        raise ValueError("No todos_list found in current task context.")
    
    # Get task labels from current context
    task_labels = _current_task_context.get("task_labels", [])
    override_activity_hours = has_override_activity_hours_label(task_labels)
    
    # Calculate timestamps for the target date
    try:
        israel_tz = pytz.timezone(config_manager.get_timezone())
    except Exception as e:
        israel_tz = pytz.timezone("Asia/Jerusalem")
    
    try:
        # Parse the target date
        target_dt = datetime.strptime(target_date, "%Y-%m-%d")
        target_dt = israel_tz.localize(target_dt)
        
        # Set start and end times for the full day
        start_timestamp = target_dt.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
        end_timestamp = target_dt.replace(hour=23, minute=59, second=59, microsecond=999999).isoformat()
        
        print(f"🗓️ Searching for available slots on {target_dt.strftime('%A, %B %d, %Y')}")
        
        result = await get_filtered_free_intervals_for_list(start_timestamp, end_timestamp, todos_list, override_activity_hours=override_activity_hours)
        
        # Add date context to the result
        result += f"\n\n🎯 Target Date: {target_dt.strftime('%A, %B %d, %Y')}"
        
        return result
        
    except ValueError:
        return f"❌ Invalid date format '{target_date}'. Please use YYYY-MM-DD format (e.g., '2024-01-15', '2024-12-25')"

async def create_todo_tool(
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
    return create_todo(title, description, start_timestamp, duration_minutes)

async def update_todo_schedule_tool(
    task_id: str,
    new_start_timestamp: str,  # ISO 8601 string in Israeli local time (Asia/Jerusalem)
    duration_minutes: int,
) -> str:
    """
    Update a todo in Todoist: schedule it at the given timestamp and set its duration.
    Args:
        task_id (str): The ID of the task to update. This must be a valid Todoist task ID.
        new_start_timestamp (str): The new start time in ISO 8601 format (Asia/Jerusalem local time, e.g. '2025-05-29T13:00:00'). Do NOT include a timezone offset; the tool will convert it to UTC.
        duration_minutes (int): The duration of the task in minutes (must be a positive integer).
    Returns:
        str: Confirmation message or error.
    Important:
        The start timestamp must be in the format 'YYYY-MM-DDTHH:MM:SS' and represent local Israel time (Asia/Jerusalem). Do NOT include a timezone offset in this parameter.
    """
    # The underlying function is synchronous, so run it in a thread
    loop = asyncio.get_event_loop()
    
    # First, update the schedule
    schedule_result = await loop.run_in_executor(None, update_todo_schedule, task_id, new_start_timestamp, duration_minutes)
    
    # If scheduling was successful, add the "AI Scheduled" label
    if "successfully" in schedule_result.lower():
        try:
            # Get current task details to preserve existing labels
            task_details = await loop.run_in_executor(None, get_task_details, task_id)
            existing_labels = task_details.get('labels', [])
            
            # Add "AI Scheduled" label if not already present
            ai_label = "AI Scheduled"
            if ai_label not in existing_labels:
                new_labels = existing_labels + [ai_label]
                # Remove "Manual Scheduled" label if present (AI is taking over)
                new_labels = [label for label in new_labels if label != "Manual Scheduled"]
                label_result = await loop.run_in_executor(None, set_todo_labels, task_id, new_labels)
                
                # Enhance the result message to indicate label was added
                schedule_result += f" AI Scheduled label applied."
        except Exception as e:
            # Don't fail the whole operation if labeling fails
            print(f"Warning: Failed to apply AI Scheduled label to task {task_id}: {e}")
            schedule_result += f" (Warning: Could not apply AI Scheduled label: {e})"
    
    return schedule_result

# Get the current timestamp in ISO 8601 format (Israel time)
try:
    israel_tz = pytz.timezone(config_manager.get_timezone())
    now_iso = datetime.now(israel_tz).replace(microsecond=0).isoformat()
except Exception as e:
    print(f"❌ Error loading timezone configuration: {e}")
    # Fallback to default timezone
    israel_tz = pytz.timezone("Asia/Jerusalem")
    now_iso = datetime.now(israel_tz).replace(microsecond=0).isoformat()

# Load settings and get model configuration
try:
    settings = config_manager.load_settings()
    model_name = settings.get("openai", {}).get("model", "gpt-4.1-nano")
except Exception as e:
    print(f"❌ Error loading settings: {e}")
    # Use default model
    model_name = "gpt-4.1-nano"

# Define a model client
model_client = OpenAIChatCompletionClient(
    model=model_name,
)

# Load system message from prompts.json
try:
    system_message = config_manager.get_agent_prompt("scheduling_agent", current_time=now_iso)
except Exception as e:
    print(f"❌ Error loading agent prompt: {e}")
    # Use fallback system message
    system_message = f"You are a helpful scheduling assistant. The current time is: {now_iso}."

# Termination condition: stop when the agent responds with a text message
termination_condition = FunctionCallTermination("update_todo_schedule_tool")

# Main workflow: expects user_input string about a new task OR task_data dict from webhook
async def schedule_initial_tasks_agent(task_input) -> str:
    # Handle both string input (original behavior) and dict input (from webhook)
    if isinstance(task_input, dict):
        # Webhook task data - extract and format
        task_data = task_input
        
        # Check if there's an explicit todos_list override from UI testing
        if 'todos_list_override' in task_data:
            todos_list = task_data['todos_list_override']
        else:
            # Determine todos_list from project_id (normal webhook behavior)
            project_id = task_data.get('project_id')
            if not project_id:
                raise ValueError("Missing project_id in task data - cannot determine todos_list")
            
            todos_list = get_todos_list_from_project_id(project_id)
            if not todos_list:
                raise ValueError(f"No todos_list mapping found for project_id: {project_id}")
        
        # Set the todos_list and task_labels in global context for tools to use
        _current_task_context["todos_list"] = todos_list
        _current_task_context["task_labels"] = task_data.get('labels', [])
        
        # Format task data for the agent (include description for scheduling hints)
        task_content = task_data.get('content', 'Untitled Task')
        task_id = task_data.get('id', 'unknown')
        priority = task_data.get('priority', 1)
        description = task_data.get('description', '')
        
        # Build the user input with description if available
        if description and description.strip():
            user_input = f"New Task: {task_content}, ID: {task_id}, Priority: {priority}, List: {todos_list}, Description: {description}"
        else:
            user_input = f"New Task: {task_content}, ID: {task_id}, Priority: {priority}, List: {todos_list}."
        
        print(f"🤖 Starting agent execution for task: '{task_content}' (ID: {task_id}, List: {todos_list})")
    else:
        # String input behavior - todos_list must be set in global context before calling this function
        todos_list = _current_task_context.get("todos_list")
        if not todos_list:
            raise ValueError("todos_list must be set in _current_task_context before calling schedule_initial_tasks_agent with string input")
        
        user_input = task_input
        
        print(f"🤖 Starting agent execution with string input (List: {todos_list})")
    
    # Create a fresh assistant instance for each request (prevents concurrency issues)
    assistant = AssistantAgent(
        name="scheduling_agent",
        model_client=model_client,
        tools=[get_free_intervals_tool, get_free_intervals_for_date_tool, update_todo_schedule_tool], # create_todo_tool]
        system_message=system_message,
        reflect_on_tool_use=True,
        model_client_stream=False,
    )
    
    # Create a fresh team instance for each run (prevents conversation state accumulation)
    team = RoundRobinGroupChat(
        [assistant],
        termination_condition=termination_condition,
    )
    
    result = ""
    try:
        async for message in team.run_stream(task=user_input):
            if hasattr(message, 'content'):
                result += str(message.content) + "\n"
            elif isinstance(message, str):
                result += message + "\n"
    except Exception as e:
        error_msg = f"Error during agent execution: {str(e)}"
        print(f"❌ {error_msg}")
        result = error_msg
    finally:
        # Only close the client if we're running as a standalone script
        # Don't close it during webhook processing as it might be reused
        if not isinstance(task_input, dict):
            try:
                await model_client.close()
            except Exception as e:
                print(f"Warning: Error closing model client: {e}")
    
    if isinstance(task_input, dict):
        task_content = task_input.get('content', 'Task')
        print(f"✅ Agent execution completed for task: '{task_content}'")
    
    return result.strip()

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 3:
        print("Usage: python master_agent.py '<user_input>' <todos_list>")
        print("  user_input: Description of the task to schedule")
        print("  todos_list: Required todos list name (e.g. 'work', 'general', etc.)")
        print("  Example: python master_agent.py 'Review project proposal' work")
        exit(1)
    
    user_input = sys.argv[1]
    todos_list = sys.argv[2]
    
    # Validate that todos_list is provided
    if not todos_list or todos_list.strip() == "":
        print("❌ Error: todos_list cannot be empty")
        print("Available lists depend on your project mappings configuration")
        exit(1)
    
    # Set the todos_list in context before running the agent
    _current_task_context["todos_list"] = todos_list
    
    # Add todos_list info to the user input for the agent
    enhanced_input = f"New Task: {user_input}, List: {todos_list}."
    
    result = asyncio.run(schedule_initial_tasks_agent(enhanced_input))
    print(result)

