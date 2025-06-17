"""
Webhook server for handling Todoist webhook events.

Dependencies:
- fastapi
- uvicorn

Install with:
  pip install fastapi uvicorn

To run: 
  uvicorn webhook_server:app --host 0.0.0.0 --port 5055 --reload
"""
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import asyncio
import json
import logging
import os
import re
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional, List
from task_processor import router
from central_logger import log_trigger_received, log_task_action
from agent_lock import agent_lock

# Set up logging
def setup_logging():
    """Set up structured logging for webhook events"""
    
    # Create logs directory if it doesn't exist
    # Note: In container environments, this directory is temporary and will be deleted on container restart
    logs_dir = Path("logs")
    logs_dir.mkdir(exist_ok=True)
    
    # Configure webhook logger
    webhook_logger = logging.getLogger("webhook_events")
    webhook_logger.setLevel(logging.INFO)
    
    # Remove existing handlers to avoid duplication
    for handler in webhook_logger.handlers[:]:
        webhook_logger.removeHandler(handler)
    
    # Create file handler for webhook events
    webhook_handler = logging.FileHandler(logs_dir / "webhook_events.log")
    webhook_handler.setLevel(logging.INFO)
    
    # Create console handler for debugging
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    
    # Create formatter for structured logging
    formatter = logging.Formatter(
        '%(asctime)s | %(levelname)s | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    webhook_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)
    
    webhook_logger.addHandler(webhook_handler)
    webhook_logger.addHandler(console_handler)
    
    return webhook_logger

# Initialize logging
webhook_logger = setup_logging()

app = FastAPI()

def save_to_recent_events(log_entry: Dict[str, Any]):
    """Save log entry to recent events file for UI access"""
    recent_events_file = Path("logs/recent_events.json")
    try:
        # Load existing recent events
        if recent_events_file.exists():
            with open(recent_events_file, 'r') as f:
                recent_events = json.load(f)
        else:
            recent_events = []
        
        # Add new event
        recent_events.append(log_entry)
        
        # Keep only last 100 events
        recent_events = recent_events[-100:]
        
        # Save back to file
        with open(recent_events_file, 'w') as f:
            json.dump(recent_events, f, indent=2)
            
    except Exception as e:
        print(f"Error saving recent events: {e}")

def log_webhook_event(event_type: str, data: Dict[str, Any], result: Optional[Dict] = None, error: Optional[str] = None):
    """Log webhook events in a structured format - DEPRECATED, use central_logger instead"""
    # This function is kept for compatibility but logs are now handled by central_logger
    # Only log errors since triggers and actions are now logged centrally
    if error:
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "event_type": f"WEBHOOK_ERROR",
            "task_id": data.get("id"),
            "task_content": data.get("content"), 
            "error": error,
            "raw_data": data
        }
        
        # Log as JSON for easy parsing
        webhook_logger.error(json.dumps(log_entry))
        save_to_recent_events(log_entry)

def extract_task_data(event_data: Dict[str, Any], event_name: str, event_data_extra: Dict[str, Any] = None) -> Dict[str, Any]:
    """
    Extract only the needed fields from the webhook event_data and include event_name.
    
    Keeps: event_name, content, id, checked, completed_at, description, due, 
           duration, labels, priority, project_id, section_id, and old_item if available
    """
    result = {
        "event_name": event_name,
        "content": event_data.get("content"),
        "id": event_data.get("id"),
        "checked": event_data.get("checked"),
        "completed_at": event_data.get("completed_at"),
        "description": event_data.get("description"),
        "due": event_data.get("due"),
        "duration": event_data.get("duration"),
        "labels": event_data.get("labels"),
        "priority": event_data.get("priority"),
        "project_id": event_data.get("project_id"),
        "section_id": event_data.get("section_id")
    }
    
    # Add old_item data if available (for change analysis)
    if event_data_extra and "old_item" in event_data_extra:
        result["old_item"] = event_data_extra["old_item"]
    
    return result

def extract_task_id_from_url(task_url: str) -> Optional[str]:
    """
    Extract task ID from Todoist URL.
    
    Example: https://app.todoist.com/app/task/6c4V3gm4qcjpwjwM -> 6c4V3gm4qcjpwjwM
    
    Args:
        task_url: Todoist task URL
        
    Returns:
        str: Task ID or None if not found
    """
    try:
        # Match pattern: /task/{task_id}
        pattern = r'/task/([a-zA-Z0-9]+)'
        match = re.search(pattern, task_url)
        if match:
            return match.group(1)
        return None
    except Exception as e:
        print(f"Error extracting task ID from URL {task_url}: {e}")
        return None

def is_task_completed(task_name: str) -> bool:
    """
    Check if task is completed by looking for checkmark symbol.
    
    Args:
        task_name: Task name from calendar event
        
    Returns:
        bool: True if task contains "✓", False otherwise
    """
    return "✓" in task_name

def log_calendar_event(event_type: str, data: Dict[str, Any], result: Optional[Dict] = None, error: Optional[str] = None):
    """Log calendar events - DEPRECATED, use central_logger instead"""
    # This function is kept for compatibility but most logs are now handled by central_logger
    # Only log errors and special calendar events
    if error:
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "event_type": f"CALENDAR_ERROR",
            "task_id": data.get("task_id"),
            "task_content": data.get("task_name"),
            "task_url": data.get("task_url"), 
            "error": error,
            "raw_data": data
        }
        
        # Log as JSON for easy parsing
        webhook_logger.error(json.dumps(log_entry))
        save_to_recent_events(log_entry)

@app.post("/webhook/todoist")
async def webhook_receiver(request: Request):
    """
    Receive Todoist webhook events, extract relevant data, and process them.
    """
    start_time = datetime.now()
    
    try:
        data = await request.json()
        
        # Extract event data
        event_name = data.get("event_name")
        event_data = data.get("event_data", {})
        event_data_extra = data.get("event_data_extra", {})
        
        if not event_name:
            error_msg = "Missing 'event_name' in webhook data"
            log_webhook_event("ERROR", data, error=error_msg)
            return JSONResponse(
                status_code=400, 
                content={"error": error_msg}
            )
        
        if not event_data:
            error_msg = "Missing 'event_data' in webhook data"
            log_webhook_event("ERROR", data, error=error_msg)
            return JSONResponse(
                status_code=400, 
                content={"error": error_msg}
            )
        
        # Extract only the fields we need (including old_item if available)
        task_data = extract_task_data(event_data, event_name, event_data_extra)
        task_id = task_data.get('id', 'unknown')
        
        # Check if agent is currently working
        if agent_lock.is_agent_working():
            lock_status = agent_lock.get_status()
            
            if lock_status['is_cooldown']:
                blocked_msg = f"Agent cooldown active (task {lock_status['current_task_id']} just finished), blocking webhook for task {task_id} ({lock_status['cooldown_remaining_seconds']:.1f}s remaining)"
                block_reason = "agent_cooldown"
            else:
                blocked_msg = f"Agent is busy working on task {lock_status['current_task_id']}, blocking webhook for task {task_id}"
                block_reason = "agent_busy"
            
            # Log that webhook was blocked
            log_entry = {
                "timestamp": datetime.now().isoformat(),
                "event_type": "WEBHOOK_BLOCKED",
                "task_id": task_id,
                "task_content": task_data.get('content'),
                "blocked_reason": block_reason,
                "current_agent_task": lock_status['current_task_id'],
                "agent_status": lock_status
            }
            save_to_recent_events(log_entry)
            
            print(f"🚫 WEBHOOK BLOCKED: {blocked_msg}")
            
            return JSONResponse(status_code=202, content={
                "status": "blocked",
                "message": blocked_msg,
                "reason": block_reason,
                "agent_status": lock_status,
                "retry_after_seconds": 5 if block_reason == "agent_cooldown" else 30,
                "timestamp": datetime.now().isoformat()
            })
        
        # Process the task event (this will handle all logging via central_logger)
        result = await router(task_data)
        
        # Calculate processing time for response
        processing_time = (datetime.now() - start_time).total_seconds()
        
        return JSONResponse(status_code=200, content={
            "status": "success",
            "message": "Webhook processed successfully",
            "event_name": event_name,
            "task_id": task_data.get('id'),
            "result": result,
            "processing_time_seconds": processing_time,
            "timestamp": datetime.now().isoformat()
        })
        
    except json.JSONDecodeError as e:
        error_msg = f"Invalid JSON format: {str(e)}"
        log_webhook_event("ERROR", {"raw_request": "invalid_json"}, error=error_msg)
        return JSONResponse(
            status_code=400, 
            content={"error": error_msg}
        )
    except Exception as e:
        error_msg = f"Processing error: {str(e)}"
        log_webhook_event("ERROR", task_data if 'task_data' in locals() else data, error=error_msg)
        return JSONResponse(
            status_code=500, 
            content={"error": error_msg}
        )

@app.post("/webhook/calendar")
async def calendar_webhook_receiver(request: Request):
    """
    Receive Google Calendar events and process incomplete tasks for rescheduling.
    Accepts either a single event (dict) or a list of events.
    Each event can be {"body": {...}} or just {...} with task_name/task_url at the top level.
    """
    start_time = datetime.now()
    
    try:
        data = await request.json()
        
        # Accept both a single event (dict) and a list of events
        if isinstance(data, dict):
            data = [data]
        elif not isinstance(data, list):
            error_msg = "Bad request - please check your parameters. Expected a dict or array of calendar events."
            log_calendar_event("ERROR", {"raw_data": data}, error=error_msg)
            return JSONResponse(
                status_code=400,
                content={"error": error_msg}
            )
        
        # Check if agent is currently working
        if agent_lock.is_agent_working():
            lock_status = agent_lock.get_status()
            
            if lock_status['is_cooldown']:
                blocked_msg = f"Agent cooldown active (task {lock_status['current_task_id']} just finished), blocking calendar webhook ({lock_status['cooldown_remaining_seconds']:.1f}s remaining)"
            else:
                blocked_msg = f"Agent is busy working on task {lock_status['current_task_id']}, blocking calendar webhook"
            
            print(f"🚫 CALENDAR WEBHOOK BLOCKED: {blocked_msg}")
            
            return JSONResponse(status_code=202, content={
                "status": "blocked",
                "message": blocked_msg,
                "reason": "agent_cooldown" if lock_status['is_cooldown'] else "agent_busy",
                "agent_status": lock_status,
                "retry_after_seconds": 5 if lock_status['is_cooldown'] else 30,
                "timestamp": datetime.now().isoformat()
            })
        
        results = []
        
        for i, event in enumerate(data):
            try:
                # Accept both {"body": {...}} and flat {...}
                if "body" in event and isinstance(event["body"], dict):
                    body = event["body"]
                else:
                    body = event
                task_name = body.get("task_name", "")
                task_url = body.get("task_url", "")
                
                if not task_name or not task_url:
                    error_msg = f"Event {i}: Missing task_name or task_url"
                    log_calendar_event("ERROR", {"event_index": i, "body": body}, error=error_msg)
                    results.append({
                        "event_index": i,
                        "status": "error",
                        "error": error_msg
                    })
                    continue
                
                # Extract task ID from URL
                task_id = extract_task_id_from_url(task_url)
                if not task_id:
                    error_msg = f"Event {i}: Could not extract task ID from URL: {task_url}"
                    log_calendar_event("ERROR", {"event_index": i, "task_url": task_url}, error=error_msg)
                    results.append({
                        "event_index": i,
                        "status": "error",
                        "error": error_msg
                    })
                    continue
                
                # Check if task is completed
                is_completed = is_task_completed(task_name)
                
                # Prepare task data for processing
                task_data = {
                    "event_name": "calendar:event_end",
                    "content": task_name.replace("✓", "").strip(),  # Remove any checkmarks
                    "id": task_id,
                }
                
                if is_completed:
                    # Task is completed, log and skip
                    log_task_action("skipped", task_data, "Task is already completed", {"reason": "task_completed"})
                    results.append({
                        "event_index": i,
                        "status": "skipped",
                        "task_id": task_id,
                        "reason": "Task is already completed",
                        "task_name": task_name
                    })
                    continue
                
                # Task is incomplete, send for rescheduling (central_logger will handle logging)
                try:
                    # Process the calendar reschedule request
                    result = await router(task_data)
                    
                    results.append({
                        "event_index": i,
                        "status": "processed",
                        "task_id": task_id,
                        "task_name": task_name,
                        "result": result
                    })
                    
                except Exception as processing_error:
                    error_msg = f"Failed to process calendar reschedule for task {task_id}: {str(processing_error)}"
                    log_task_action("failed", task_data, error_msg, {"error": str(processing_error)})
                    
                    results.append({
                        "event_index": i,
                        "status": "error",
                        "task_id": task_id,
                        "task_name": task_name,
                        "error": error_msg
                    })
                
            except Exception as event_error:
                error_msg = f"Event {i}: Error processing event: {str(event_error)}"
                log_calendar_event("ERROR", {"event_index": i, "event": event}, error=error_msg)
                results.append({
                    "event_index": i,
                    "status": "error",
                    "error": error_msg
                })
        
        # Calculate processing time for response
        processing_time = (datetime.now() - start_time).total_seconds()
        
        return JSONResponse(status_code=200, content={
            "status": "success",
            "message": f"Calendar webhook processed {len(data)} events",
            "results": results,
            "processing_time_seconds": processing_time,
            "timestamp": datetime.now().isoformat()
        })
        
    except json.JSONDecodeError as e:
        error_msg = f"Invalid JSON format: {str(e)}"
        log_calendar_event("ERROR", {"raw_request": "invalid_json"}, error=error_msg)
        return JSONResponse(
            status_code=400,
            content={"error": error_msg}
        )
    except Exception as e:
        error_msg = f"Calendar webhook processing error: {str(e)}"
        log_calendar_event("ERROR", {"raw_data": data if 'data' in locals() else {}}, error=error_msg)
        return JSONResponse(
            status_code=500,
            content={"error": error_msg}
        )

@app.get("/webhook/logs")
async def get_recent_logs():
    """Get recent webhook events for the UI"""
    try:
        recent_events_file = Path("logs/recent_events.json")
        if recent_events_file.exists():
            with open(recent_events_file, 'r') as f:
                events = json.load(f)
            return {"events": events}
        else:
            return {"events": []}
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"error": f"Failed to read logs: {str(e)}"}
        )

@app.get("/webhook/agent-status")
async def get_agent_status():
    """Get current agent lock status"""
    try:
        status = agent_lock.get_status()
        return {
            "agent_status": status,
            "is_accepting_webhooks": not agent_lock.is_agent_working(),
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"error": f"Failed to get agent status: {str(e)}"}
        )

@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy", 
        "timestamp": datetime.now().isoformat(),
        "service": "Todoist Webhook Processor"
    }

@app.get("/")
async def root():
    """Root endpoint with service info."""
    return {
        "service": "Todoist Webhook Processor",
        "version": "1.0.0",
        "endpoints": {
            "webhook": "POST /webhook/todoist - Process Todoist webhooks",
            "calendar": "POST /webhook/calendar - Process Google Calendar events",
            "logs": "GET /webhook/logs - Get recent webhook events",
            "agent_status": "GET /webhook/agent-status - Get agent lock status",
            "health": "GET /health - Health check"
        },
        "timestamp": datetime.now().isoformat()
    }

if __name__ == "__main__":
    import uvicorn
    from config_manager import config_manager
    config = config_manager.get_webhook_config()
    uvicorn.run(app, host=config["host"], port=config["port"], reload=True) 