"""
Task processor for handling Todoist webhook events.

This module contains the main routing logic for processing task events
from Todoist webhooks after data extraction.
"""
import asyncio
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional, List
import pytz
from master_agent import schedule_initial_tasks_agent
import requests
import os
from central_logger import log_trigger_received, log_task_action
from agent_lock import agent_working
from config_manager import config_manager
from google_calendar import get_todos_list_from_project_id

def has_manual_scheduled_label(task_data: Dict[str, Any]) -> bool:
    """
    Check if a task has the 'Manual Scheduled' label.
    
    Args:
        task_data: Task data containing labels field
        
    Returns:
        bool: True if task has 'Manual Scheduled' label, False otherwise
    """
    labels = task_data.get('labels', [])
    if not labels:
        return False
    
    # Check for various forms of the manual scheduled label
    manual_scheduled_variants = [
        'Manual Scheduled',
        'manual scheduled', 
        'Manual scheduled',
        'manual_scheduled',
        'ManualScheduled'
    ]
    
    return any(label in manual_scheduled_variants for label in labels)

def has_ai_scheduled_label(task_data: Dict[str, Any]) -> bool:
    """
    Check if a task has the 'AI Scheduled' label.
    
    Args:
        task_data: Task data containing labels field
        
    Returns:
        bool: True if task has 'AI Scheduled' label, False otherwise
    """
    labels = task_data.get('labels', [])
    if not labels:
        return False
    
    # Check for various forms of the AI scheduled label
    ai_scheduled_variants = [
        'AI Scheduled',
        'ai scheduled', 
        'Ai Scheduled',
        'ai_scheduled',
        'AIScheduled'
    ]
    
    return any(label in ai_scheduled_variants for label in labels)

def should_auto_schedule_by_priority(task_data: Dict[str, Any], todos_list: str) -> tuple[bool, str]:
    """
    Check if a task should be auto-scheduled based on its priority level.
    
    Args:
        task_data: Task data containing priority field
        todos_list: Todo list name for determining priority threshold
        
    Returns:
        tuple: (should_schedule: bool, reason: str)
    """
    priority = task_data.get('priority')  # This can be None, 1, 2, 3, or 4 (Todoist API values)
    
    try:
        should_schedule = config_manager.should_auto_schedule_task(priority, todos_list)
        
        if should_schedule:
            # Normalize priority for display: None or 1 both represent Low priority
            effective_priority = 1 if priority is None else priority
            return True, f"Priority {effective_priority} meets auto-scheduling threshold for {todos_list} list"
        else:
            # Get the settings for better error message
            settings = config_manager.load_settings()
            auto_scheduling_settings = settings.get("auto_scheduling_priority", {})
            list_settings = auto_scheduling_settings.get(todos_list, {})
            
            # Handle backward compatibility
            if isinstance(list_settings, int):
                # Convert old format to new API format
                old_priority = list_settings
                threshold = 5 - old_priority  # Map old 1->4, old 2->3, old 3->2, old 4->1
                is_enabled = True  # Default to enabled for old format
            else:
                threshold = list_settings.get("min_priority", 1)
                is_enabled = list_settings.get("enabled", True)
            
            # Check if auto-scheduling is disabled for this list
            if not is_enabled:
                return False, f"Auto-scheduling is disabled for {todos_list} list"
            
            # Map API priority values to user-friendly names
            api_priority_names = {4: "Urgent (P1)", 3: "High (P2)", 2: "Normal (P3)", 1: "Low (P4)"}
            
            # Normalize priority for display: None or 1 both represent Low priority
            effective_priority = 1 if priority is None else priority
            threshold_name = api_priority_names.get(threshold, f"API Priority {threshold}")
            current_name = api_priority_names.get(effective_priority, f"API Priority {effective_priority}")
            return False, f"Priority {effective_priority} ({current_name}) below auto-scheduling threshold (requires {threshold_name} or higher for {todos_list} list)"
            
    except Exception as e:
        print(f"Error checking auto-scheduling priority: {e}")
        # Default to allowing auto-scheduling if there's an error
        effective_priority = 1 if priority is None else priority
        return True, f"Priority check failed for priority {effective_priority}, defaulting to auto-schedule (error: {str(e)})"

def analyze_task_changes(current_data: Dict[str, Any], old_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Analyze what exactly changed between the old and current task data.
    
    Args:
        current_data: Current task data from event_data
        old_data: Previous task data from event_data_extra.old_item
        
    Returns:
        Dict containing change analysis with fields changed, their old/new values, and change summary
    """
    changes = {
        "has_changes": False,
        "fields_changed": [],
        "change_details": {},
        "change_summary": [],
        "significant_changes": []
    }
    
    # Define important fields to track
    important_fields = {
        "content": "Task title/content",
        "due": "Due date",
        "duration": "Duration", 
        "priority": "Priority",
        "labels": "Labels",
        "description": "Description",
        "project_id": "Project",
        "section_id": "Section",
        "checked": "Completion status"
    }
    
    for field, field_description in important_fields.items():
        old_value = old_data.get(field)
        new_value = current_data.get(field)
        
        # Check if values are different
        if old_value != new_value:
            changes["has_changes"] = True
            changes["fields_changed"].append(field)
            
            # Store detailed change info
            changes["change_details"][field] = {
                "old_value": old_value,
                "new_value": new_value,
                "description": field_description
            }
            
            # Create human-readable change summary
            if field == "due":
                if old_value is None and new_value is not None:
                    due_str = new_value.get('string', 'Unknown') if isinstance(new_value, dict) else str(new_value)
                    changes["change_summary"].append(f"Due date added: {due_str}")
                    changes["significant_changes"].append("due_date_added")
                elif old_value is not None and new_value is None:
                    changes["change_summary"].append("Due date removed")
                    changes["significant_changes"].append("due_date_removed")
                elif old_value is not None and new_value is not None:
                    old_str = old_value.get('string', 'Unknown') if isinstance(old_value, dict) else str(old_value)
                    new_str = new_value.get('string', 'Unknown') if isinstance(new_value, dict) else str(new_value)
                    changes["change_summary"].append(f"Due date changed: {old_str} → {new_str}")
                    changes["significant_changes"].append("due_date_changed")
                    
            elif field == "duration":
                if old_value is None and new_value is not None:
                    duration_str = f"{new_value.get('amount', '?')} {new_value.get('unit', 'minutes')}" if isinstance(new_value, dict) else str(new_value)
                    changes["change_summary"].append(f"Duration added: {duration_str}")
                    changes["significant_changes"].append("duration_added")
                elif old_value is not None and new_value is None:
                    changes["change_summary"].append("Duration removed")
                    changes["significant_changes"].append("duration_removed")
                elif old_value is not None and new_value is not None:
                    old_str = f"{old_value.get('amount', '?')} {old_value.get('unit', 'minutes')}" if isinstance(old_value, dict) else str(old_value)
                    new_str = f"{new_value.get('amount', '?')} {new_value.get('unit', 'minutes')}" if isinstance(new_value, dict) else str(new_value)
                    changes["change_summary"].append(f"Duration changed: {old_str} → {new_str}")
                    changes["significant_changes"].append("duration_changed")
                    
            elif field == "content":
                changes["change_summary"].append(f"Title changed: '{old_value}' → '{new_value}'")
                changes["significant_changes"].append("title_changed")
                
            elif field == "priority":
                priority_names = {1: "Low", 2: "Normal", 3: "High", 4: "Urgent"}
                old_name = priority_names.get(old_value, f"Priority {old_value}")
                new_name = priority_names.get(new_value, f"Priority {new_value}")
                changes["change_summary"].append(f"Priority changed: {old_name} → {new_name}")
                changes["significant_changes"].append("priority_changed")
                
            elif field == "labels":
                old_labels = old_value if isinstance(old_value, list) else []
                new_labels = new_value if isinstance(new_value, list) else []
                added_labels = set(new_labels) - set(old_labels)
                removed_labels = set(old_labels) - set(new_labels)
                
                if added_labels:
                    changes["change_summary"].append(f"Labels added: {', '.join(added_labels)}")
                if removed_labels:
                    changes["change_summary"].append(f"Labels removed: {', '.join(removed_labels)}")
                if added_labels or removed_labels:
                    changes["significant_changes"].append("labels_changed")
                    
            elif field == "description":
                if old_value == "" and new_value != "":
                    changes["change_summary"].append("Description added")
                elif old_value != "" and new_value == "":
                    changes["change_summary"].append("Description removed")
                else:
                    changes["change_summary"].append("Description modified")
                changes["significant_changes"].append("description_changed")
                
            elif field == "checked":
                if new_value and not old_value:
                    changes["change_summary"].append("Task completed")
                    changes["significant_changes"].append("task_completed")
                elif not new_value and old_value:
                    changes["change_summary"].append("Task reopened")
                    changes["significant_changes"].append("task_reopened")
                    
            else:
                # Generic change description
                changes["change_summary"].append(f"{field_description} changed: {old_value} → {new_value}")
    
    return changes

async def router(task_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Main router function for Todoist webhook events.
    
    Routes events to the correct handler based on event_name.
    
    Args:
        task_data: Extracted task data containing event_name and task fields
        
    Returns:
        Dict with processing result
    """
    event_name = task_data.get('event_name')
    
    if not event_name:
        return {
            "status": "error",
            "error": "Missing event_name in task_data",
            "processed_at": datetime.now().isoformat()
        }
    
    # Log the trigger received
    trigger_type_map = {
        "item:added": "task_created",
        "item:updated": "task_updated", 
        "item:completed": "task_completed",
        "item:deleted": "task_deleted",
        "calendar:event_end": "calendar_event_end"
    }
    
    trigger_type = trigger_type_map.get(event_name, f"unknown_{event_name}")
    log_trigger_received(trigger_type, task_data)
    
    try:
        # Route to the appropriate handler
        if event_name == "item:added":
            result = await handle_task_added(task_data)
        elif event_name == "item:updated":
            result = await handle_task_updated(task_data)
        elif event_name == "item:completed":
            result = await handle_task_completed(task_data)
        elif event_name == "item:deleted":
            result = await handle_task_deleted(task_data)
        elif event_name == "calendar:event_end":
            result = await handle_calendar_reschedule(task_data)
        else:
            result = await handle_unknown_event(task_data, event_name)
        
        return {
            "status": "success",
            "event_name": event_name,
            "task_id": task_data.get('id'),
            "task_content": task_data.get('content'),
            "result": result,
            "processed_at": datetime.now().isoformat()
        }
        
    except Exception as e:
        # Log failed action
        log_task_action("failed", task_data, f"Processing failed: {str(e)}")
        
        return {
            "status": "error",
            "event_name": event_name,
            "task_id": task_data.get('id'),
            "error": str(e),
            "processed_at": datetime.now().isoformat()
        }

async def handle_task_added(task_data: Dict[str, Any]) -> str:
    """Handle when a new task is added to Todoist."""
    task_content = task_data.get('content', 'Unknown Task')
    task_id = task_data.get('id', 'unknown')
    project_id = task_data.get('project_id')
    
    # First, check if this project is configured for auto-categorization
    if project_id:
        from autocategorizer import autocategorize_task
        try:
            result = await autocategorize_task(task_data)
            # Only return if categorization was actually performed
            if "not configured for auto-categorization" not in result:
                log_task_action("categorized", task_data, result, {"reason": "auto_categorization"})
                return result
        except Exception as e:
            error_msg = f"Failed to auto-categorize task: {str(e)}"
            log_task_action("failed", task_data, error_msg, {"error": str(e)})
            print(f"❌ Auto-categorization error: {error_msg}")
            # Continue with normal task handling if categorization fails
    
    # If not configured for auto-categorization or categorization failed, proceed with normal task handling
    # Check if task has Manual Scheduled label
    if has_manual_scheduled_label(task_data):
        result_msg = f"Task '{task_content}' skipped - marked as manually scheduled. The AI will not interfere with this task's scheduling."
        log_task_action("skipped", task_data, result_msg, {"reason": "manual_scheduled_label"})
        return result_msg
    
    if not project_id:
        result_msg = f"Task '{task_content}' skipped - no project_id found. Cannot determine todos_list for priority checking."
        log_task_action("skipped", task_data, result_msg, {"reason": "no_project_id"})
        return result_msg
    
    todos_list = get_todos_list_from_project_id(project_id)
    if not todos_list:
        result_msg = f"Task '{task_content}' skipped - no todos_list mapping found for project_id: {project_id}"
        log_task_action("skipped", task_data, result_msg, {"reason": "no_todos_list_mapping", "project_id": project_id})
        return result_msg
    
    # Check if task priority meets auto-scheduling threshold
    should_schedule, priority_reason = should_auto_schedule_by_priority(task_data, todos_list)
    if not should_schedule:
        result_msg = f"Task '{task_content}' skipped - {priority_reason}"
        log_task_action("skipped", task_data, result_msg, {"reason": "priority_below_threshold", "priority_check": priority_reason})
        return result_msg
    
    try:
        # Use agent lock to prevent cascading webhooks
        async with agent_working(task_id, "scheduling new task"):
            # Pass the task data directly to the master agent
            agent_result = await schedule_initial_tasks_agent(task_data)
            result_msg = f"Task scheduled successfully: {agent_result}"
            log_task_action("rescheduled", task_data, result_msg, {"agent_result": agent_result})
            return result_msg
    except Exception as e:
        error_msg = f"Failed to schedule task: {str(e)}"
        log_task_action("failed", task_data, error_msg, {"error": str(e)})
        return error_msg

async def handle_task_updated(task_data: Dict[str, Any]) -> str:
    """Handle when a task is updated in Todoist."""
    task_content = task_data.get('content', 'Unknown Task')
    task_id = task_data.get('id', 'unknown')
    
    # Check if task has Manual Scheduled label
    if has_manual_scheduled_label(task_data):
        result_msg = f"Task update processed - '{task_content}' is marked as manually scheduled, so no automatic scheduling changes were made."
        log_task_action("skipped", task_data, result_msg, {"reason": "manual_scheduled_label"})
        return result_msg
    
    # Analyze what changed if we have old_item data
    change_analysis = None
    if "old_item" in task_data:
        old_item = task_data["old_item"]
        current_item = {k: v for k, v in task_data.items() if k != "old_item"}  # Exclude old_item from current data
        change_analysis = analyze_task_changes(current_item, old_item)
        
        if change_analysis["has_changes"]:
            change_summary = "; ".join(change_analysis["change_summary"])
            
            # Determine if we should trigger rescheduling based on significant changes
            significant_changes = change_analysis["significant_changes"]
            
            # Check for priority change - if priority changed, we should reschedule regardless of due date
            priority_changed = "priority_changed" in significant_changes
            
            # Only reschedule if the task is overdue (due date + duration is in the past) OR priority changed
            should_reschedule = False
            reschedule_reason = None
            
            # Priority change scheduling logic
            if priority_changed:
                should_reschedule = True
                old_priority = old_item.get('priority')
                new_priority = task_data.get('priority')
                priority_names = {1: "Low", 2: "Normal", 3: "High", 4: "Urgent"}
                # Normalize None to 1 since Todoist defaults unset priority to Low (1)
                old_effective = 1 if old_priority is None else old_priority
                new_effective = 1 if new_priority is None else new_priority
                old_name = priority_names.get(old_effective, f"Priority {old_effective}")
                new_name = priority_names.get(new_effective, f"Priority {new_effective}")
                reschedule_reason = f"Priority changed from {old_name} to {new_name}"
            
            # Check if task has a due date and if it's overdue (only if not already rescheduling due to priority)
            if not should_reschedule:
                current_due = task_data.get('due')
                if current_due and isinstance(current_due, dict):
                    due_date_str = current_due.get('date')  # This is in ISO format with timezone
                    if due_date_str:
                        try:
                            # Parse the due date (comes as UTC ISO string like "2025-06-01T15:00:00Z")
                            from datetime import datetime, timedelta
                            import pytz
                            
                            # Parse the UTC due date
                            if due_date_str.endswith('Z'):
                                due_date_utc = datetime.fromisoformat(due_date_str.replace('Z', '+00:00'))
                            else:
                                due_date_utc = datetime.fromisoformat(due_date_str)
                            
                            # Convert to local timezone for comparison
                            from config_manager import config_manager
                            try:
                                settings = config_manager.load_settings()
                                timezone = settings.get("timezone", "Asia/Jerusalem")
                                local_tz = pytz.timezone(timezone)
                            except:
                                local_tz = pytz.timezone("Asia/Jerusalem")
                            
                            # Get current time in the same timezone
                            now_local = datetime.now(local_tz)
                            due_date_local = due_date_utc.astimezone(local_tz)
                            
                            # Calculate the task end time (due date + duration)
                            task_end_time = due_date_local
                            duration_minutes = 0
                            
                            # Add duration if available
                            duration = task_data.get('duration')
                            if duration and isinstance(duration, dict):
                                duration_amount = duration.get('amount', 0)
                                duration_unit = duration.get('unit', 'minute')
                                
                                # Convert duration to minutes
                                if duration_unit == 'minute':
                                    duration_minutes = duration_amount
                                elif duration_unit == 'hour':
                                    duration_minutes = duration_amount * 60
                                elif duration_unit == 'day':
                                    duration_minutes = duration_amount * 24 * 60
                                
                                # Add duration to due date to get actual end time
                                task_end_time = due_date_local + timedelta(minutes=duration_minutes)
                            
                            # Check if the task is actually overdue (end time has passed)
                            if task_end_time < now_local:
                                should_reschedule = True
                                if duration_minutes > 0:
                                    reschedule_reason = f"Task is overdue (due: {due_date_local.strftime('%Y-%m-%d %H:%M')}, duration: {duration_minutes}min, end: {task_end_time.strftime('%Y-%m-%d %H:%M')}, now: {now_local.strftime('%Y-%m-%d %H:%M')})"
                                else:
                                    reschedule_reason = f"Task is overdue (due: {due_date_local.strftime('%Y-%m-%d %H:%M')}, no duration, now: {now_local.strftime('%Y-%m-%d %H:%M')})"
                            
                        except Exception as e:
                            print(f"⚠️ Error parsing due date '{due_date_str}': {e}")
                            # If we can't parse the date, don't reschedule
                            should_reschedule = False
            
            if should_reschedule:
                try:
                    # Use agent lock to prevent cascading webhooks
                    async with agent_working(task_id, "rescheduling task"):
                        # Use the master agent to reschedule the task
                        project_id = task_data.get('project_id')
                        
                        if project_id:
                            todos_list = get_todos_list_from_project_id(project_id)
                            if todos_list:
                                # Check if task priority meets auto-scheduling threshold
                                should_schedule, priority_reason = should_auto_schedule_by_priority(task_data, todos_list)
                                if not should_schedule:
                                    result_msg = f"Task update processed but rescheduling skipped - {priority_reason}. Changes: {change_summary}."
                                    log_task_action("skipped", task_data, result_msg, {
                                        "reason": "priority_below_threshold",
                                        "priority_check": priority_reason,
                                        "changes": change_summary
                                    })
                                    return result_msg
                                
                                # Set the todos_list override for the agent
                                task_data['todos_list_override'] = todos_list
                                
                                agent_result = await schedule_initial_tasks_agent(task_data)
                                
                                # Clean up agent result to extract just the final message
                                cleaned_result = agent_result
                                if agent_result:
                                    # Split by lines and find the last meaningful line (not function calls/results)
                                    lines = agent_result.strip().split('\n')
                                    # Look for the last line that doesn't start with '[' (function calls/results)
                                    for line in reversed(lines):
                                        line = line.strip()
                                        if line and not line.startswith('[') and not line.startswith('FunctionCall') and not line.startswith('FunctionExecutionResult'):
                                            cleaned_result = line
                                            break
                                
                                result_msg = f"Task updated and rescheduled - {reschedule_reason}. Changes: {change_summary}. Agent result: {cleaned_result}"
                                log_task_action("rescheduled", task_data, result_msg, {
                                    "reason": reschedule_reason,
                                    "changes": change_summary,
                                    "agent_result": cleaned_result
                                })
                                return result_msg
                            else:
                                print(f"⚠️ No todos_list mapping found for project_id: {project_id}")
                        else:
                            print(f"⚠️ No project_id found for task {task_id}")
                        
                except Exception as e:
                    error_msg = f"Task changes detected ({change_summary}) but rescheduling failed: {str(e)}"
                    log_task_action("failed", task_data, error_msg, {
                        "changes": change_summary,
                        "error": str(e)
                    })
                    return error_msg
            else:
                # No rescheduling needed
                if priority_changed:
                    # Priority changed but might not meet threshold or other criteria
                    result_msg = f"Task updated successfully: {change_summary}. Priority change detected but no rescheduling triggered."
                else:
                    result_msg = f"Task updated successfully: {change_summary}. No rescheduling needed (task is not overdue)."
                log_task_action("ignored", task_data, result_msg, {
                    "reason": "no_rescheduling_needed",
                    "changes": change_summary
                })
                return result_msg
                
        else:
            result_msg = "Task update processed - no significant changes detected."
            log_task_action("ignored", task_data, result_msg, {"reason": "no_significant_changes"})
            return result_msg
    else:
        result_msg = "Task update processed - change analysis not available (no old_item data)."
        log_task_action("ignored", task_data, result_msg, {"reason": "no_old_item_data"})
        return result_msg

async def handle_task_completed(task_data: Dict[str, Any]) -> str:
    """Handle when a task is completed in Todoist."""
    # Remove scheduling from the task
    from todoist import remove_task_scheduling
    task_id = task_data.get('id')
    remove_result = None
    if task_id:
        remove_result = remove_task_scheduling(task_id)
    else:
        remove_result = "No task_id provided, could not remove scheduling."

    # TODO: Implement your logic for completed tasks
    # Examples:
    # - Remove from calendar
    # - Log completion time and productivity metrics
    # - Trigger follow-up actions
    # - Update project progress
    
    # Placeholder logic - replace with your actual implementation
    await asyncio.sleep(0.1)  # Simulate some processing
    
    result_msg = f"Task completion processed successfully. {remove_result}"
    log_task_action("completed", task_data, result_msg)
    return result_msg

async def handle_task_deleted(task_data: Dict[str, Any]) -> str:
    """Handle when a task is deleted from Todoist."""
    # TODO: Implement your logic for deleted tasks
    # Examples:
    # - Remove from calendar
    # - Clean up related data
    # - Cancel reminders
    # - Log deletion for analytics
    
    # Placeholder logic - replace with your actual implementation
    await asyncio.sleep(0.1)  # Simulate some processing
    
    result_msg = "Task deletion processed successfully"
    log_task_action("deleted", task_data, result_msg)
    return result_msg

async def handle_calendar_reschedule(task_data: Dict[str, Any]) -> str:
    """Handle calendar-triggered task rescheduling."""
    task_id = task_data.get('id')
    task_content = task_data.get('content', 'Unknown Task')
    
    try:
        # Get complete task details from Todoist API
        from todoist import get_task_details
        
        try:
            complete_task_data = get_task_details(task_id)
        except ValueError as e:
            # Task not found - it might have been deleted
            result_msg = f"Task {task_id} not found in Todoist (may have been deleted): {str(e)}"
            log_task_action("failed", task_data, result_msg, {"error": str(e)})
            return result_msg
        except Exception as e:
            result_msg = f"Failed to fetch task details from Todoist: {str(e)}"
            log_task_action("failed", task_data, result_msg, {"error": str(e)})
            return result_msg
        
        # Merge the complete task data with our partial data
        enhanced_task_data = {
            "event_name": "calendar:event_end",
            "content": complete_task_data.get('content', task_content),
            "id": task_id,
            "priority": complete_task_data.get('priority', 1),
            "project_id": complete_task_data.get('project_id'),
            "checked": complete_task_data.get('is_completed', False),
            "description": complete_task_data.get('description'),
            "due": complete_task_data.get('due'),
            "duration": complete_task_data.get('duration'),
            "labels": complete_task_data.get('labels', []),
            "section_id": complete_task_data.get('section_id')
        }
        
        # Check if task has Manual Scheduled label - skip rescheduling if it does
        if has_manual_scheduled_label(enhanced_task_data):
            result_msg = f"Calendar reschedule skipped for task '{task_content}' - marked as manually scheduled. The AI will not interfere with this task's scheduling."
            log_task_action("skipped", enhanced_task_data, result_msg, {"reason": "manual_scheduled_label"})
            return result_msg
        
        # --- Project ID enrichment: map numeric to string if needed ---
        project_id = enhanced_task_data.get('project_id')
        mapped_project_id = project_id
        if project_id and str(project_id).isdigit():
            # Map numeric project ID to new string ID
            API_TOKEN = os.getenv("TODOIST_API_TOKEN")
            url = f"https://api.todoist.com/api/v1/id_mappings/projects/{project_id}"
            headers = {"Authorization": f"Bearer {API_TOKEN}"}
            try:
                resp = requests.get(url, headers=headers)
                if resp.status_code == 200:
                    mapping_list = resp.json()
                    for mapping in mapping_list:
                        if mapping.get("old_id") == str(project_id):
                            mapped_project_id = mapping.get("new_id")
                            break
                    if mapped_project_id != project_id:
                        print(f"Mapped numeric project_id {project_id} -> {mapped_project_id}")
                        enhanced_task_data["project_id"] = mapped_project_id
                    else:
                        print(f"Could not map numeric project_id {project_id}, using as is.")
                else:
                    print(f"Failed to map project_id {project_id}: {resp.status_code} {resp.text}")
            except Exception as e:
                print(f"Exception mapping project_id {project_id}: {e}")
        
        # Determine the todos_list from project_id (now mapped if needed)
        project_id = enhanced_task_data.get('project_id')
        
        if not project_id:
            result_msg = f"Task {task_id} has no project_id - cannot determine scheduling category"
            log_task_action("failed", enhanced_task_data, result_msg, {"error": "no_project_id"})
            return result_msg
        
        todos_list = get_todos_list_from_project_id(project_id)
        if not todos_list:
            result_msg = f"No todos_list mapping found for project_id: {project_id}"
            log_task_action("failed", enhanced_task_data, result_msg, {"error": "no_todos_list_mapping"})
            return result_msg
        
        # Set the todos_list override for the agent
        enhanced_task_data['todos_list_override'] = todos_list
        
        # Check if task priority meets auto-scheduling threshold
        should_schedule, priority_reason = should_auto_schedule_by_priority(enhanced_task_data, todos_list)
        if not should_schedule:
            result_msg = f"Calendar reschedule skipped for task '{task_content}' - {priority_reason}"
            log_task_action("skipped", enhanced_task_data, result_msg, {
                "reason": "priority_below_threshold",
                "priority_check": priority_reason,
                "trigger": "calendar"
            })
            return result_msg
        
        try:
            # Use agent lock to prevent cascading webhooks
            async with agent_working(task_id, "calendar reschedule"):
                # Use the master agent to reschedule the task
                agent_result = await schedule_initial_tasks_agent(enhanced_task_data)
                
                result_msg = f"Calendar-triggered reschedule completed: {agent_result}"
                log_task_action("rescheduled", enhanced_task_data, result_msg, {
                    "trigger": "calendar",
                    "todos_list": todos_list,
                    "agent_result": agent_result
                })
                return result_msg
        except Exception as e:
            error_msg = f"Failed to reschedule task from calendar: {str(e)}"
            log_task_action("failed", task_data, error_msg, {"error": str(e)})
            return error_msg
        
    except Exception as e:
        error_msg = f"Failed to reschedule task from calendar: {str(e)}"
        log_task_action("failed", task_data, error_msg, {"error": str(e)})
        return error_msg

async def handle_unknown_event(task_data: Dict[str, Any], event_name: str) -> str:
    """Handle unknown or unsupported event types."""
    # TODO: Consider adding a handler for this event type
    
    result_msg = f"Unknown event type '{event_name}' - no handler implemented"
    log_task_action("ignored", task_data, result_msg, {"reason": "unknown_event_type"})
    return result_msg 