"""
Auto-categorization module for Todoist tasks.

This module handles the automatic categorization of tasks into appropriate sections
for any configured Todoist project using AutoGen for AI-driven classification.
"""
from typing import Dict, Any, Optional, List
import os
from todoist import get_project_sections, move_task_to_section
from autogen_agentchat.agents import AssistantAgent
from autogen_agentchat.conditions import FunctionCallTermination
from autogen_agentchat.teams import RoundRobinGroupChat
from autogen_ext.models.openai import OpenAIChatCompletionClient
from config_manager import config_manager
from datetime import datetime
import pytz

async def get_project_sections_with_descriptions(project_id: str) -> List[Dict[str, Any]]:
    """
    Get all sections from a Todoist project with their names and descriptions.
    
    Args:
        project_id: The Todoist project ID
        
    Returns:
        List of section objects with id, name, and other properties
    """
    try:
        sections = get_project_sections(project_id)
        return sections
    except Exception as e:
        print(f"❌ Error getting sections for project {project_id}: {e}")
        return []

def get_section_id_by_name(sections: List[Dict[str, Any]], section_name: str) -> Optional[str]:
    """
    Get the section ID by its name (case-insensitive).
    
    Args:
        sections: List of section objects from Todoist
        section_name: Name of the section to find
        
    Returns:
        Optional[str]: Section ID if found, None otherwise
    """
    section_name_lower = section_name.lower().strip()
    for section in sections:
        if section.get("name", "").lower().strip() == section_name_lower:
            return section["id"]
    return None

async def classify_task_into_section(
    task_content: str, 
    task_description: str,
    sections: List[Dict[str, Any]], 
    project_context: str = ""
) -> Optional[str]:
    """
    Classify a task into the most appropriate section using AutoGen.
    
    Args:
        task_content: The content/title of the task
        task_description: The description of the task (can be empty)
        sections: List of section objects from Todoist
        project_context: Additional context about the project type
        
    Returns:
        Optional[str]: Section ID if a match is found, None otherwise
    """
    if not sections:
        return None
    
    # Get current timestamp for the agent
    try:
        israel_tz = pytz.timezone(config_manager.get_timezone())
        now_iso = datetime.now(israel_tz).replace(microsecond=0).isoformat()
    except Exception as e:
        print(f"❌ Error loading timezone configuration: {e}")
        israel_tz = pytz.timezone("Asia/Jerusalem")
        now_iso = datetime.now(israel_tz).replace(microsecond=0).isoformat()

    # Load settings and get model configuration
    try:
        settings = config_manager.load_settings()
        model_name = settings.get("openai", {}).get("model", "gpt-4.1-nano")
    except Exception as e:
        print(f"❌ Error loading settings: {e}")
        model_name = "gpt-4.1-nano"

    # Create model client
    model_client = OpenAIChatCompletionClient(
        model=model_name,
    )

    # Build the available sections list with better mapping for Hebrew
    sections_list = "\n".join([f"- {section.get('name', 'Unnamed')}" for section in sections])
    
    # Create system message for the categorization task
    system_message = f"""You are a grocery item categorization assistant. Your task is to categorize Hebrew grocery items into the most appropriate section.

The current time is: {now_iso}

Available sections in this grocery project:
{sections_list}

Section meanings:
- חלבי = Dairy products (milk, cheese, yogurt, butter)
- בשר = Meat products (beef, chicken, turkey, sausages)
- ירקות ופירות = Fruits and vegetables (fresh produce)
- חטיפים = Snacks (chips, crackers, sweets)
- יבשים = Dry goods (rice, pasta, cereals, grains)
- אלכוהול = Alcoholic beverages (beer, wine, spirits)
- אחר = Other items that don't fit the above categories

{f"Project context: {project_context}" if project_context else ""}

You should:
1. Analyze the Hebrew grocery item name and description carefully
2. Match the item to the most appropriate section based on its category
3. Respond with ONLY the exact section name as it appears in the list above
4. If no section is clearly appropriate, respond with "NONE"

Common Hebrew grocery items and their sections:
- חלב → חלבי
- גבינה → חלבי
- יוגורט → חלבי
- בשר → בשר
- עוף → בשר
- תפוחים → ירקות ופירות
- עגבניות → ירקות ופירות
- אורז → יבשים
- פסטה → יבשים
- צ'יפס → חטיפים
- ביסקוויטים → חטיפים
- בירה → אלכוהול
- יין → אלכוהול

Task to categorize:
Title: {task_content}
Description: {task_description if task_description else "No description provided"}

Remember: Respond with ONLY the exact section name or "NONE"."""

    # Create the assistant agent
    assistant = AssistantAgent(
        name="task_categorizer",
        model_client=model_client,
        system_message=system_message,
        reflect_on_tool_use=True,
        model_client_stream=False,
    )

    # Create the team with a simple termination condition
    team = RoundRobinGroupChat([assistant])

    # Run the classification
    result = ""
    try:
        message_count = 0
        async for message in team.run_stream(task="Please categorize this grocery item into the appropriate section."):
            message_count += 1
            if hasattr(message, 'content'):
                result += str(message.content) + "\n"
            elif isinstance(message, str):
                result += message + "\n"
            
            # Prevent infinite loops - stop after reasonable number of messages
            if message_count >= 2:
                break
                
    except Exception as e:
        print(f"❌ Error during classification: {e}")
        return None
    finally:
        try:
            # Close the client properly after getting the result
            await model_client.close()
        except Exception as e:
            print(f"Warning: Error closing model client: {e}")

    # Clean up the result to get just the section name
    section_name = result.strip()
    
    # Remove any extra formatting or explanation
    lines = section_name.split('\n')
    
    # Look for the actual section name in the response
    # Check each line to see if it matches one of our section names
    available_section_names = [s.get('name', '') for s in sections]
    
    for line in lines:
        line = line.strip()
        if line in available_section_names:
            section_name = line
            break
    else:
        # If no exact match found, try the last non-empty line that's not the task
        for line in reversed(lines):
            line = line.strip()
            if (line and 
                not line.startswith('Please categorize') and 
                not line.startswith('#') and 
                not line.startswith('*') and 
                not line.startswith('I ') and
                line != "Please categorize this grocery item into the appropriate section."):
                section_name = line
                break
    
    # Check if the model said no categorization is appropriate
    if section_name.upper() == "NONE":
        return None
    
    # Find the matching section ID
    return get_section_id_by_name(sections, section_name)

def is_project_configured_for_autocategorization(project_id: str) -> bool:
    """
    Check if a project is configured for auto-categorization.
    
    Args:
        project_id: The Todoist project ID
        
    Returns:
        bool: True if the project should use auto-categorization
    """
    try:
        settings = config_manager.load_settings()
        autocategorization_config = settings.get("autocategorization", {})
        enabled_projects = autocategorization_config.get("enabled_projects", [])
        
        # Support both project IDs and project names/todos_list names
        from google_calendar import get_todos_list_from_project_id
        todos_list = get_todos_list_from_project_id(project_id)
        
        return project_id in enabled_projects or todos_list in enabled_projects
        
    except Exception as e:
        print(f"❌ Error checking autocategorization config: {e}")
        return False

def get_project_context(project_id: str) -> str:
    """
    Get additional context for a project to help with categorization.
    
    Args:
        project_id: The Todoist project ID
        
    Returns:
        str: Context description for the project
    """
    try:
        settings = config_manager.load_settings()
        autocategorization_config = settings.get("autocategorization", {})
        project_contexts = autocategorization_config.get("project_contexts", {})
        
        # Try project ID first, then todos_list name
        context = project_contexts.get(project_id)
        if not context:
            from google_calendar import get_todos_list_from_project_id
            todos_list = get_todos_list_from_project_id(project_id)
            context = project_contexts.get(todos_list, "")
            
        return context
        
    except Exception as e:
        print(f"❌ Error getting project context: {e}")
        return ""

async def autocategorize_task(task_data: Dict[str, Any]) -> str:
    """
    Auto-categorize a task into the appropriate section if the project is configured for it.
    
    Args:
        task_data: Task data from Todoist webhook
        
    Returns:
        str: Result message
    """
    task_id = task_data.get('id')
    task_content = task_data.get('content', '')
    task_description = task_data.get('description', '')
    project_id = task_data.get('project_id')
    
    if not task_id or not project_id:
        return "Cannot categorize task - missing task_id or project_id"
    
    # Check if this project is configured for auto-categorization
    if not is_project_configured_for_autocategorization(project_id):
        return f"Project {project_id} is not configured for auto-categorization"
    
    try:
        # Get all sections from the project
        sections = await get_project_sections_with_descriptions(project_id)
        
        if not sections:
            return "No sections found in project - cannot categorize"
        
        # Get project context for better categorization
        project_context = get_project_context(project_id)
        
        # Classify the task
        section_id = await classify_task_into_section(
            task_content, 
            task_description, 
            sections, 
            project_context
        )
        
        if section_id:
            # Validate section_id is not empty or None
            if not section_id.strip():
                return "Error: Empty section ID returned from classification"
            
            # Find section name for logging first
            section_name = "Unknown"
            section_found = False
            for section in sections:
                if section.get("id") == section_id:
                    section_name = section.get("name", "Unknown")
                    section_found = True
                    break
            
            if not section_found:
                return f"Error: Section ID '{section_id}' not found in project sections"
            
            # Move the task to the appropriate section
            try:
                result = move_task_to_section(task_id, section_id)
                return f"Task auto-categorized into section '{section_name}': {result}"
            except Exception as e:
                return f"Task auto-categorized into section '{section_name}': Error moving task - {str(e)}"
        else:
            return "No appropriate section found for the task"
            
    except Exception as e:
        return f"Error auto-categorizing task: {str(e)}" 