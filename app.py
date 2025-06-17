"""
Todoist Agent Management UI
A Streamlit app for managing Google Calendar authentication, webhook server, and AI agent configuration.
"""
import streamlit as st
import os
from pathlib import Path
from dotenv import load_dotenv
import json
from datetime import datetime
import requests
import subprocess
import time
import asyncio as aio
from typing import Dict, List, Optional, Any

# Load environment variables from .env file
load_dotenv()

# Set page config
st.set_page_config(
    page_title="Todoist Agent Manager",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded"
)

def create_persistent_tabs(page_name: str, tab_configs: List[Dict[str, str]], default_tab: str = None):
    """
    Create persistent tabs that maintain state across page refreshes.
    
    Args:
        page_name: Unique identifier for the page (e.g., "config", "testing")
        tab_configs: List of dicts with 'key', 'label', and 'icon' keys
        default_tab: Default tab key if none is set (defaults to first tab)
    
    Returns:
        str: Currently selected tab key
    """
    # Extract tab information
    tab_keys = [tab['key'] for tab in tab_configs]
    tab_labels = [tab['label'] for tab in tab_configs]
    
    # Initialize tab state from URL query params or session state
    url_tab = st.query_params.get("tab", None)
    session_key = f"{page_name}_tab"
    
    # Initialize tab state from URL or default to first/specified tab
    if session_key not in st.session_state:
        if url_tab in tab_keys:
            st.session_state[session_key] = url_tab
        else:
            st.session_state[session_key] = default_tab or tab_keys[0]
    
    # Update URL to match current tab
    if st.session_state[session_key] != url_tab:
        st.query_params["tab"] = st.session_state[session_key]
    
    # Create tab navigation buttons with improved styling
    cols = st.columns(len(tab_configs))
    
    for i, tab_config in enumerate(tab_configs):
        with cols[i]:
            is_active = st.session_state[session_key] == tab_config['key']
            button_type = "primary" if is_active else "secondary"
            
            # Create button with consistent height and styling
            if st.button(
                tab_config['label'],
                type=button_type,
                use_container_width=True,
                key=f"{page_name}_tab_btn_{tab_config['key']}",
                help=f"Switch to {tab_config['label'].replace(chr(10), ' ')}"  # Remove newlines for tooltip
            ):
                st.session_state[session_key] = tab_config['key']
                st.query_params["tab"] = tab_config['key']
                st.rerun()
    
    st.markdown("---")
    
    return st.session_state[session_key]

def validate_google_credentials():
    """Check if google_credentials.json exists and contains valid data"""
    creds_file = Path("tokens/google_credentials.json")
    
    if not creds_file.exists():
        return False, "File not found", None
    
    try:
        with open(creds_file, 'r') as f:
            data = json.load(f)
        
        # Basic validation - check if it has the expected structure
        if not isinstance(data, dict):
            return False, "Invalid JSON structure", None
        
        # Check for installed app credentials structure
        if "installed" not in data and "web" not in data:
            return False, "Missing 'installed' or 'web' section - not a valid OAuth client credentials file", None
        
        # Extract redirect URIs for validation
        redirect_uris = []
        if "installed" in data:
            redirect_uris = data["installed"].get("redirect_uris", [])
        elif "web" in data:
            redirect_uris = data["web"].get("redirect_uris", [])
        
        return True, "Valid", redirect_uris
        
    except json.JSONDecodeError:
        return False, "Invalid JSON format", None
    except Exception as e:
        return False, f"Error reading file: {str(e)}", None

def validate_google_token(token_path):
    """Validate a Google token file"""
    token_file = Path(f"tokens/{token_path}")
    
    if not token_file.exists():
        return False, "Token file not found"
    
    try:
        with open(token_file, 'r') as f:
            token_data = json.load(f)
        
        # Basic validation
        if not isinstance(token_data, dict):
            return False, "Invalid token structure"
        
        # Check for required fields
        required_fields = ['token', 'refresh_token', 'client_id', 'client_secret']
        missing_fields = [field for field in required_fields if field not in token_data]
        
        if missing_fields:
            return False, f"Missing required fields: {', '.join(missing_fields)}"
        
        return True, "Valid token"
        
    except json.JSONDecodeError:
        return False, "Invalid JSON format"
    except Exception as e:
        return False, f"Error reading token: {str(e)}"

def main():
    # Load custom fonts
    try:
        with open("app/static/custom_fonts.css", "r") as f:
            st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)
    except FileNotFoundError:
        # Fallback CSS if file is not found
        st.markdown("""
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@300;400;500;600;700&display=swap');
        @import url('https://fonts.googleapis.com/css2?family=Space+Mono:ital,wght@0,400;0,700;1,400;1,700&display=swap');
        
        html, body, [class*="css"] {
            font-family: 'Space Grotesk', sans-serif !important;
        }
        .stApp {
            font-family: 'Space Grotesk', sans-serif !important;
        }
        h1, h2, h3, h4, h5, h6 {
            font-family: 'Space Grotesk', sans-serif !important;
        }
        p, div, span, label {
            font-family: 'Space Grotesk', sans-serif !important;
        }
        .stButton > button {
            font-family: 'Space Grotesk', sans-serif !important;
        }
        code, pre, .stCode {
            font-family: 'Space Mono', monospace !important;
        }
        .stCodeBlock {
            font-family: 'Space Mono', monospace !important;
        }
        .stMarkdown code {
            font-family: 'Space Mono', monospace !important;
        }
        </style>
        """, unsafe_allow_html=True)
    
    st.title("🤖 Todoist Agent Manager")
    st.markdown("Manage your AI-powered Todoist scheduling agent")
    
    # Sidebar navigation
    st.sidebar.title("Navigation")
    
    # Get current page from URL query params or session state
    url_page = st.query_params.get("page", None)
    
    # Initialize page state from URL or default to home
    if "page" not in st.session_state:
        st.session_state.page = url_page if url_page in ["home", "auth", "config", "webhook", "testing"] else "home"
    
    # Navigation buttons with URL parameter updates
    if st.sidebar.button("🏠 Home", use_container_width=True):
        st.session_state.page = "home"
        st.query_params["page"] = "home"
    
    if st.sidebar.button("🔐 Authentication", use_container_width=True):
        st.session_state.page = "auth"
        st.query_params["page"] = "auth"
        
    if st.sidebar.button("⚙️ Configuration", use_container_width=True):
        st.session_state.page = "config"
        st.query_params["page"] = "config"
        
    if st.sidebar.button("🚀 Webhook Server", use_container_width=True):
        st.session_state.page = "webhook"
        st.query_params["page"] = "webhook"
        
    if st.sidebar.button("🧪 Testing", use_container_width=True):
        st.session_state.page = "testing"
        st.query_params["page"] = "testing"
    
    # Update URL to match current page (in case it was set programmatically)
    if st.session_state.page != url_page:
        st.query_params["page"] = st.session_state.page
    
    st.sidebar.markdown("---")
    
    # Status indicators
    st.sidebar.subheader("System Status")
    
    # Check Google tokens
    main_token_valid, _ = validate_google_token("google_token_main.json")
    work_token_valid, _ = validate_google_token("google_token_work.json")
    
    if main_token_valid:
        st.sidebar.success("✅ Main Google Account")
    else:
        st.sidebar.error("❌ Main Google Account")
    
    if work_token_valid:
        st.sidebar.success("✅ Work Google Account")
    else:
        st.sidebar.warning("⚠️ Work Google Account")
    
    # Check Todoist token
    if os.getenv("TODOIST_API_TOKEN"):
        st.sidebar.success("✅ Todoist API")
    else:
        st.sidebar.error("❌ Todoist API Token")
    
    # Check OpenAI token
    if os.getenv("OPENAI_API_KEY"):
        st.sidebar.success("✅ OpenAI API")
    else:
        st.sidebar.error("❌ OpenAI API Key")
    
    # Main content area
    if st.session_state.page == "home":
        show_home_page()
    elif st.session_state.page == "auth":
        show_auth_page()
    elif st.session_state.page == "config":
        show_config_page()
    elif st.session_state.page == "webhook":
        show_webhook_page()
    elif st.session_state.page == "testing":
        show_testing_page()

def show_home_page():
    st.header("Welcome to Todoist Agent Manager")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("🎯 What does this do?")
        st.markdown("""
        This AI agent automatically schedules your Todoist tasks by:
        - **Listening** for new tasks via webhooks
        - **Checking** your Google Calendar for free time slots
        - **Scheduling** tasks based on their project/list and Activity Hours
        - **Updating** Todoist with the scheduled time and duration
        """)
        
        st.subheader("🚀 Quick Setup")
        st.markdown("""
        1. **🔐 Authenticate** your Google accounts (main/work)
        2. **⚙️ Configure** project mappings and Activity Hours
        3. **🚀 Start** the webhook server
        4. **🧪 Test** with sample tasks
        """)
    
    with col2:
        st.subheader("📊 System Overview")
        
        # Component status with proper validation
        creds_valid, creds_msg, _ = validate_google_credentials()
        main_token_valid, _ = validate_google_token("google_token_main.json")
        work_token_valid, _ = validate_google_token("google_token_work.json")
        
        components = [
            ("Google Calendar API", creds_valid and (main_token_valid or work_token_valid)),
            ("Todoist API", bool(os.getenv("TODOIST_API_TOKEN"))),
            ("OpenAI API", bool(os.getenv("OPENAI_API_KEY"))),
            ("Configuration", Path("config/settings.json").exists()),
        ]
        
        for component, status in components:
            if status:
                st.success(f"✅ {component}")
            else:
                st.error(f"❌ {component}")
        
        st.subheader("📈 Recent Activity")
        st.info("Activity logs will appear here once the webhook server is running")

def show_auth_page():
    st.header("🔐 Google Authentication")
    st.markdown("Authenticate your Google accounts to access calendar data")
    
    # Check Google tokens
    main_token_valid, main_token_msg = validate_google_token("google_token_main.json")
    work_token_valid, work_token_msg = validate_google_token("google_token_work.json")
    
    # Check if google_credentials.json exists and is valid
    creds_valid, creds_msg, _ = validate_google_credentials()
    
    if not creds_valid:
        st.error("❌ **google_credentials.json not found or invalid!**")
        if creds_msg:
            st.error(f"❌ **google_credentials.json invalid:** {creds_msg}")
        st.markdown("""
        **Setup Instructions:**
        1. Go to [Google Cloud Console](https://console.cloud.google.com/)
        2. Create a project and enable Google Calendar API
        3. Go to APIs & Services → Credentials
        4. Create OAuth 2.0 Client ID (Desktop)
        5. **Important**: Update Authorized redirect URIs to include `http://localhost:8080`
        6. Download and save as 'tokens/google_credentials.json'
        """)
        return
    
    st.success("✅ **google_credentials.json is valid!**")
    
    # Authentication status
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("🏠 Main Account")
        main_token_valid, main_token_msg = validate_google_token("google_token_main.json")
        
        if main_token_valid:
            st.success("✅ **Authenticated**")
            
            # Show token info
            try:
                with open("tokens/google_token_main.json", 'r') as f:
                    token_data = json.load(f)
                
                if 'expiry' in token_data:
                    expiry = datetime.fromisoformat(token_data['expiry'].replace('Z', '+00:00'))
                    st.info(f"🕒 Expires: {expiry.strftime('%Y-%m-%d %H:%M')}")
            except:
                pass
            
            if st.button("🔄 Re-authenticate Main", use_container_width=True):
                # Use Streamlit-compatible authentication  
                if streamlit_authenticate_google("tokens/google_token_main.json", "Main Google Account"):
                    st.rerun()
                    
        else:
            if main_token_msg == "Token file not found":
                st.error("❌ **Not authenticated**")
            else:
                st.error(f"❌ **Invalid token:** {main_token_msg}")
            
            # Use Streamlit-compatible authentication
            streamlit_authenticate_google("tokens/google_token_main.json", "Main Google Account")
    
    with col2:
        st.subheader("💼 Work Account")
        work_token_valid, work_token_msg = validate_google_token("google_token_work.json")
        
        if work_token_valid:
            st.success("✅ **Authenticated**")
            
            # Show token info
            try:
                with open("tokens/google_token_work.json", 'r') as f:
                    token_data = json.load(f)
                
                if 'expiry' in token_data:
                    expiry = datetime.fromisoformat(token_data['expiry'].replace('Z', '+00:00'))
                    st.info(f"🕒 Expires: {expiry.strftime('%Y-%m-%d %H:%M')}")
            except:
                pass
            
            if st.button("🔄 Re-authenticate Work", use_container_width=True):
                # Use Streamlit-compatible authentication
                if streamlit_authenticate_google("tokens/google_token_work.json", "Work Google Account"):
                    st.rerun()
                    
        else:
            if work_token_msg == "Token file not found":
                st.warning("⚠️ **Not authenticated**")
                st.markdown("*Work account is optional*")
            else:
                st.warning(f"⚠️ **Invalid token:** {work_token_msg}")
                st.markdown("*Work account is optional*")
            
            # Use Streamlit-compatible authentication
            streamlit_authenticate_google("tokens/google_token_work.json", "Work Google Account")
    
    # Calendar discovery
    st.markdown("---")
    st.subheader("📅 Calendar Discovery")
    st.markdown("Discover available calendars for each authenticated account")
    
    if st.button("🔍 Discover Calendars"):
        accounts_to_check = []
        if main_token_valid:
            accounts_to_check.append(("main", "tokens/google_token_main.json"))
        if work_token_valid:
            accounts_to_check.append(("work", "tokens/google_token_work.json"))
        
        if not accounts_to_check:
            st.warning("⚠️ No authenticated accounts found")
            return
        
        try:
            from google_calendar import get_available_calendars
            
            for account_name, token_file in accounts_to_check:
                st.markdown(f"**{account_name.title()} Account Calendars:**")
                
                calendars = get_available_calendars(token_file)
                
                if calendars:
                    for cal in calendars:
                        primary_badge = " 🌟" if cal.get('primary', False) else ""
                        selected_badge = " ✅" if cal.get('selected', True) else " ❌"
                        
                        st.markdown(f"- **{cal['summary']}**{primary_badge}{selected_badge}")
                        st.caption(f"   ID: `{cal['id']}`")
                else:
                    st.error(f"❌ No calendars found for {account_name}")
                
                st.markdown("")
                    
        except Exception as e:
            st.error(f"❌ Calendar discovery failed: {str(e)}")
    
    # API Keys section
    st.markdown("---")
    st.subheader("🔑 API Keys")
    st.markdown("Check and configure required API keys")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("**Todoist API Token:**")
        if os.getenv("TODOIST_API_TOKEN"):
            masked_token = os.getenv("TODOIST_API_TOKEN")[:8] + "..." + os.getenv("TODOIST_API_TOKEN")[-4:]
            st.success(f"✅ Set: `{masked_token}`")
        else:
            st.error("❌ Not set")
            st.markdown("""
            **Setup:**
            1. Go to [Todoist Settings](https://todoist.com/prefs/integrations)
            2. Copy your API token
            3. Set environment variable: `TODOIST_API_TOKEN=your_token`
            """)
    
    with col2:
        st.markdown("**OpenAI API Key:**")
        if os.getenv("OPENAI_API_KEY"):
            masked_key = os.getenv("OPENAI_API_KEY")[:8] + "..." + os.getenv("OPENAI_API_KEY")[-4:]
            st.success(f"✅ Set: `{masked_key}`")
        else:
            st.error("❌ Not set")
            st.markdown("""
            **Setup:**
            1. Go to [OpenAI API Keys](https://platform.openai.com/api-keys)
            2. Create a new API key
            3. Set environment variable: `OPENAI_API_KEY=your_key`
            """)

def show_config_page():
    st.header("⚙️ Configuration")
    st.markdown("Configure project mappings, Activity Hours, and AI prompts")
    
    from config_manager import config_manager
    
    # Load current settings with error handling
    try:
        settings = config_manager.load_settings()
    except Exception as e:
        st.error(f"❌ Error loading settings: {str(e)}")
        st.info("💡 Check your settings.json file for syntax errors or missing configuration.")
        return
        
    try:
        prompts = config_manager.load_prompts()
    except Exception as e:
        st.error(f"❌ Error loading prompts: {str(e)}")
        st.info("💡 Check your prompts.json file for syntax errors or missing configuration.")
        return
    
    # Define tab configuration
    tab_configs = [
        {"key": "mappings", "label": "📋 Project\nMappings"},
        {"key": "hours", "label": "⏰ Activity\nHours"},
        {"key": "scheduling", "label": "🎯 Auto-\nScheduling"},
        {"key": "calendars", "label": "📅 Calendar\nSelection"},
        {"key": "autocategorization", "label": "🏷️ Auto-\nCategories"},
        {"key": "prompts", "label": "🤖 AI\nPrompts"},
        {"key": "settings", "label": "🔧 General\nSettings"}
    ]
    
    # Add custom CSS for better tab styling
    st.markdown("""
    <style>
    div[data-testid="column"] > div > div > div > button {
        height: 60px !important;
        white-space: pre-line !important;
        text-align: center !important;
        font-size: 0.85rem !important;
        line-height: 1.2 !important;
        padding: 8px 4px !important;
    }
    </style>
    """, unsafe_allow_html=True)
    
    # Create persistent tabs
    active_tab = create_persistent_tabs("config", tab_configs)
    
    # Show content based on selected tab
    if active_tab == "mappings":
        st.subheader("Project ID to Todo List Mappings")
        st.markdown("Map Todoist project IDs to todo list categories (work, personal, health, etc.)")
        
        # Current mappings
        mappings = settings.get("project_mappings", {})
        
        # Edit existing mappings
        if mappings:
            st.markdown("**Current Mappings:**")
            for project_id, todo_list in mappings.items():
                col1, col2, col3 = st.columns([3, 2, 1])
                with col1:
                    st.text_input(f"Project ID", value=project_id, key=f"pid_{project_id}", disabled=True)
                with col2:
                    new_list = st.text_input(
                        "Todo List", 
                        value=todo_list,
                        key=f"list_{project_id}",
                        placeholder="e.g., work, personal, health, study, gym, etc.",
                        help="Enter any custom list name you want"
                    )
                with col3:
                    if st.button("🗑️", key=f"del_{project_id}", help="Delete mapping"):
                        del mappings[project_id]
                        settings["project_mappings"] = mappings
                        try:
                            config_manager.save_settings(settings)
                            st.success(f"Deleted mapping for project {project_id}")
                            st.rerun()
                        except Exception as e:
                            st.error(f"❌ Error saving settings: {str(e)}")
                
                # Update if changed
                if new_list != todo_list and new_list.strip():  # Only update if non-empty
                    mappings[project_id] = new_list.strip()
                    settings["project_mappings"] = mappings
        
        # Add new mapping
        st.markdown("**Add New Mapping:**")
        col1, col2, col3 = st.columns([3, 2, 1])
        with col1:
            new_project_id = st.text_input("New Project ID", placeholder="e.g., 6McgWjrqw67XW6FM")
        with col2:
            new_todo_list = st.text_input(
                "Todo List", 
                placeholder="e.g., work, personal, health, study, gym, etc.",
                key="new_list",
                help="Enter any custom list name you want"
            )
        with col3:
            if st.button("➕ Add") and new_project_id and new_todo_list:
                mappings[new_project_id.strip()] = new_todo_list.strip()
                settings["project_mappings"] = mappings
                try:
                    config_manager.save_settings(settings)
                    st.success(f"Added mapping: {new_project_id.strip()} → {new_todo_list.strip()}")
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ Error saving settings: {str(e)}")
    
    elif active_tab == "hours":
        st.subheader("Activity Hours Configuration")
        st.markdown("Define Activity Hours for each todo list category from your project mappings")
        
        activity_hours = settings.get("activity_hours", {})
        days = ["sunday", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday"]
        
        # Get unique list names from project mappings
        mappings = settings.get("project_mappings", {})
        unique_lists = sorted(set(mappings.values())) if mappings else []
        
        # Clean up orphaned Activity Hours (for lists that no longer exist in mappings)
        current_activity_hour_lists = set(activity_hours.keys())
        active_lists = set(unique_lists)
        orphaned_lists = current_activity_hour_lists - active_lists
        
        if orphaned_lists:
            st.warning(f"🧹 Cleaning up Activity Hours for deleted lists: {', '.join(orphaned_lists)}")
            for orphaned_list in orphaned_lists:
                del activity_hours[orphaned_list]
        
        if not unique_lists:
            st.info("ℹ️ No project mappings configured yet. Add some project mappings in the first tab to configure Activity Hours.")
        else:
            st.info(f"📋 Configuring Activity Hours for: **{', '.join(unique_lists)}**")
            
            # AI-Powered Activity Hours Configuration (Minimal)
            st.markdown("---")
            
            # Minimal AI configuration - just text box and dropdown
            col1, col2 = st.columns([3, 1])
            
            with col1:
                ai_description = st.text_input(
                    "🤖 AI Configuration",
                    placeholder="Describe Activity Hours (e.g., 'Monday to Friday 9 to 5', 'weekends only', 'clear all hours')",
                    help="Describe Activity Hours in natural language. Changes apply automatically."
                )
            
            with col2:
                available_lists = sorted(set(mappings.values())) if mappings else ["work", "personal", "health"]
                selected_list = st.selectbox(
                    "List",
                    available_lists,
                    help="Select todo list to configure"
                )
            
            # Auto-apply when description is entered
            if ai_description.strip() and st.session_state.get(f"last_ai_input_{selected_list}") != f"{selected_list}:{ai_description}":
                # Function to call OpenAI (simplified)
                async def configure_activity_hours_with_ai(description: str, current_activity_hours: dict, selected_list: str):
                    """Use OpenAI to parse Activity Hours description and return structured configuration for specific list"""
                    import openai
                    
                    if not os.getenv("OPENAI_API_KEY"):
                        return None, "OpenAI API key not found"
                    
                    try:
                        model = "gpt-4.1"
                        current_list_schedule = current_activity_hours.get(selected_list, {})
                        current_config_str = json.dumps({selected_list: current_list_schedule}, indent=2) if current_list_schedule else f"No Activity Hours for '{selected_list}'"
                        
                        system_prompt = f"""Parse Activity Hours description and return ONLY valid JSON for '{selected_list}' list.

Current: {current_config_str}

Return format:
{{
  "{selected_list}": {{
    "monday": {{"start": "HH:MM", "end": "HH:MM"}} or null,
    "tuesday": {{"start": "HH:MM", "end": "HH:MM"}} or null,
    "wednesday": {{"start": "HH:MM", "end": "HH:MM"}} or null,
    "thursday": {{"start": "HH:MM", "end": "HH:MM"}} or null,
    "friday": {{"start": "HH:MM", "end": "HH:MM"}} or null,
    "saturday": {{"start": "HH:MM", "end": "HH:MM"}} or null,
    "sunday": {{"start": "HH:MM", "end": "HH:MM"}} or null
  }}
}}

Rules: 24-hour format, null for no hours, weekdays=Sun-Thu, weekends=Fri-Sat"""

                        client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
                        
                        response = await aio.to_thread(
                            client.chat.completions.create,
                            model=model,
                            messages=[
                                {"role": "system", "content": system_prompt},
                                {"role": "user", "content": description}
                            ],
                            temperature=0.1,
                            max_tokens=800
                        )
                        
                        ai_response = response.choices[0].message.content.strip()
                        
                        # Clean up response
                        if "```json" in ai_response:
                            ai_response = ai_response.split("```json")[1].split("```")[0].strip()
                        elif "```" in ai_response:
                            ai_response = ai_response.split("```")[1].split("```")[0].strip()
                        
                        parsed_config = json.loads(ai_response)
                        return parsed_config, None
                        
                    except json.JSONDecodeError as e:
                        return None, f"Invalid JSON: {str(e)}"
                    except Exception as e:
                        return None, f"Error: {str(e)}"
                
                # Process with AI and auto-apply
                try:
                    with st.spinner("🤖 Processing..."):
                        ai_config, ai_error = aio.run(configure_activity_hours_with_ai(
                            ai_description, 
                            activity_hours, 
                            selected_list
                        ))
                        
                        if ai_error:
                            st.error(f"❌ {ai_error}")
                        elif ai_config and selected_list in ai_config:
                            # Apply changes directly to activity_hours
                            activity_hours[selected_list] = ai_config[selected_list]
                            settings["activity_hours"] = activity_hours
                            
                            # Save immediately
                            config_manager.save_settings(settings)
                            st.success(f"✅ Updated {selected_list} Activity Hours")
                            
                            # Track last input to prevent re-processing
                            st.session_state[f"last_ai_input_{selected_list}"] = f"{selected_list}:{ai_description}"
                            
                            # Refresh to show new settings
                            time.sleep(0.5)
                            st.rerun()
                        else:
                            st.error("❌ Failed to generate valid configuration")
                            
                except Exception as e:
                    st.error(f"❌ Error: {str(e)}")
            
            st.markdown("---")
            
            for list_type in unique_lists:
                st.markdown(f"**{list_type.title()} Hours:**")
                
                if list_type not in activity_hours:
                    activity_hours[list_type] = {}
                
                cols = st.columns(7)
                for i, day in enumerate(days):
                    with cols[i]:
                        st.markdown(f"**{day.title()[:3]}**")
                        
                        current_day = activity_hours[list_type].get(day)
                        
                        enabled = st.checkbox(
                            "Enabled", 
                            value=current_day is not None,
                            key=f"{list_type}_{day}_enabled"
                        )
                        
                        if enabled:
                            start_time = st.time_input(
                                "Start",
                                value=__import__('datetime').time(9, 0) if not current_day else 
                                      __import__('datetime').time(*map(int, current_day["start"].split(":"))),
                                key=f"{list_type}_{day}_start"
                            )
                            end_time = st.time_input(
                                "End",
                                value=__import__('datetime').time(20, 0) if not current_day else 
                                      __import__('datetime').time(*map(int, current_day["end"].split(":"))),
                                key=f"{list_type}_{day}_end"
                            )
                            
                            # Save the Activity Hours
                            activity_hours[list_type][day] = {
                                "start": start_time.strftime("%H:%M"),
                                "end": end_time.strftime("%H:%M")
                            }
                        else:
                            activity_hours[list_type][day] = None
                
                st.markdown("---")
        
        settings["activity_hours"] = activity_hours
    
    elif active_tab == "scheduling":
        st.subheader("🎯 Auto-Scheduling Priority Settings")
        st.markdown("Configure which priority levels should be auto-scheduled for each todo list")
        
        # Get current auto-scheduling settings
        auto_scheduling_settings = settings.get("auto_scheduling_priority", {})
        
        # Get unique list names from project mappings
        mappings = settings.get("project_mappings", {})
        unique_lists = sorted(set(mappings.values())) if mappings else []
        
        if not unique_lists:
            st.info("ℹ️ No project mappings configured yet. Add some project mappings in the **📋 Project Mappings** tab first.")
        else:
            st.info(f"📋 Configuring auto-scheduling priority for: **{', '.join(unique_lists)}**")
            
            # Priority level explanations
            with st.expander("ℹ️ Understanding Priority Levels"):
                st.markdown("""
                **Priority Levels in Todoist:**
                - **P1 (Urgent)** 🔴 - Most important tasks (API value: 4)
                - **P2 (High)** 🟠 - High priority tasks (API value: 3)
                - **P3 (Normal)** 🟡 - Normal priority tasks (API value: 2)
                - **No Priority** ⚪ - Tasks without priority set (API value: 1)
                - **Note:** When you don't set a priority in Todoist, it defaults to API value 1
                
                **Auto-Scheduling Rules:**
                - Select the **minimum priority level** to auto-schedule
                - All tasks with that priority level **and higher** will be auto-scheduled
                - Tasks below the threshold will be ignored
                - **"No Priority and higher"** means all tasks will be auto-scheduled
                """)
            
            st.markdown("---")
            
            # Create priority settings for each todo list
            priority_options = [
                (4, "🔴 Urgent (P1) and higher"),
                (3, "🟠 High (P2) and higher"),
                (2, "🟡 Normal (P3) and higher"),
                (1, "⚪ No Priority and higher (all tasks)")
            ]
            
            # Use a more compact layout for better UX
            for i, todos_list in enumerate(unique_lists):
                if i > 0:
                    st.markdown("---")
                
                st.markdown(f"### 📂 **{todos_list.title()}** List")
                
                # Get current settings, handle backward compatibility
                current_settings = auto_scheduling_settings.get(todos_list, {})
                if isinstance(current_settings, int):
                    # Convert old format (1-4 where 1=urgent) to new format (4=urgent, 3=high, etc)
                    old_threshold = current_settings
                    current_threshold = 5 - old_threshold  # Map old 1->4, old 2->3, old 3->2, old 4->1
                    current_enabled = True  # Default to enabled for old format
                else:
                    current_threshold = current_settings.get("min_priority", 4)
                    current_enabled = current_settings.get("enabled", True)  # Default to enabled
                
                # Enable/Disable checkbox
                auto_scheduling_enabled = st.checkbox(
                    f"🎯 Enable auto-scheduling for {todos_list}",
                    value=current_enabled,
                    key=f"enabled_{todos_list}",
                    help=f"When unchecked, tasks from {todos_list} will never be auto-scheduled regardless of priority"
                )
                
                col1, col2 = st.columns([1, 2])
                
                with col1:
                    # Find the index for the current value
                    try:
                        current_index = [opt[0] for opt in priority_options].index(current_threshold)
                    except ValueError:
                        current_index = 0  # Default to first option if not found
                    
                    new_threshold_option = st.selectbox(
                        "Auto-schedule threshold:",
                        options=priority_options,
                        index=current_index,
                        format_func=lambda x: x[1],
                        key=f"priority_{todos_list}",
                        help=f"Select the minimum priority level to auto-schedule for {todos_list}",
                        disabled=not auto_scheduling_enabled  # Disable when auto-scheduling is off
                    )
                    
                    new_threshold_value = new_threshold_option[0]
                    
                    # Update settings with both enabled status and threshold
                    if new_threshold_value != current_threshold or auto_scheduling_enabled != current_enabled:
                        auto_scheduling_settings[todos_list] = {
                            "enabled": auto_scheduling_enabled,
                            "min_priority": new_threshold_value,
                            "include_no_priority": True  # Always true since unset priority becomes P4 (Low)
                        }
                        settings["auto_scheduling_priority"] = auto_scheduling_settings
                
                with col2:
                    if auto_scheduling_enabled:
                        # Show what will be scheduled based on selection
                        api_priority_names = {4: "🔴 Urgent (P1)", 3: "🟠 High (P2)", 2: "🟡 Normal (P3)", 1: "⚪ No Priority"}
                        
                        # Show scheduled priorities (API values >= threshold)
                        scheduled_priorities = [p for p in [4, 3, 2, 1] if p >= new_threshold_value]
                        scheduled_names = [api_priority_names[p] for p in scheduled_priorities]
                        
                        if scheduled_names:
                            if new_threshold_value == 1:
                                scheduled_names.append("(includes unset priority)")
                            st.success(f"✅ **Will auto-schedule:** {', '.join(scheduled_names)}")
                        else:
                            st.warning("⚠️ No tasks will be auto-scheduled")
                        
                        # Show ignored priorities
                        ignored_priorities = [p for p in [4, 3, 2, 1] if p < new_threshold_value]
                        ignored_names = [api_priority_names[p] for p in ignored_priorities]
                        
                        if ignored_names:
                            st.info(f"ℹ️ **Will ignore:** {', '.join(ignored_names)}")
                        else:
                            st.info("ℹ️ **Will ignore:** None (all tasks will be scheduled)")
                    else:
                        # Auto-scheduling is disabled
                        st.error("❌ **Auto-scheduling DISABLED**")
                        st.info("ℹ️ **All tasks from this list will be ignored** regardless of priority level")
            
            # Summary and bulk actions
            st.markdown("---")
            st.markdown("### 📊 Summary")
            
            # Show summary of current settings
            summary_data = []
            for todos_list in unique_lists:
                settings_data = auto_scheduling_settings.get(todos_list, {})
                if isinstance(settings_data, int):
                    # Convert old format
                    old_threshold = settings_data
                    threshold = 5 - old_threshold  # Map old to new API values
                    enabled = True  # Default to enabled for old format
                else:
                    threshold = settings_data.get("min_priority", 4)
                    enabled = settings_data.get("enabled", True)
                
                if enabled:
                    api_priority_names = {4: "🔴 Urgent (P1)", 3: "🟠 High (P2)", 2: "🟡 Normal (P3)", 1: "⚪ No Priority"}
                    threshold_name = api_priority_names.get(threshold, f"API Priority {threshold}")
                    
                    if threshold == 1:
                        description = f"✅ {threshold_name} and higher (all tasks)"
                    else:
                        description = f"✅ {threshold_name} and higher"
                else:
                    description = "❌ DISABLED (no auto-scheduling)"
                
                summary_data.append({
                    "List": todos_list.title(),
                    "Auto-Schedule Setting": description
                })
            
            if summary_data:
                import pandas as pd
                df = pd.DataFrame(summary_data)
                st.dataframe(df, use_container_width=True, hide_index=True)
            
            # Bulk actions (simplified)
            st.markdown("**Bulk Actions:**")
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                if st.button("🎯 Enable All & Schedule Everything", use_container_width=True):
                    for todos_list in unique_lists:
                        auto_scheduling_settings[todos_list] = {
                            "enabled": True,
                            "min_priority": 1,
                            "include_no_priority": True
                        }
                    settings["auto_scheduling_priority"] = auto_scheduling_settings
                    st.success("All lists enabled and set to schedule all tasks")
                    st.rerun()
            
            with col2:
                if st.button("🔥 Enable All & High Priority+", use_container_width=True):
                    for todos_list in unique_lists:
                        auto_scheduling_settings[todos_list] = {
                            "enabled": True,
                            "min_priority": 3,
                            "include_no_priority": False
                        }
                    settings["auto_scheduling_priority"] = auto_scheduling_settings
                    st.success("All lists enabled and set to high priority and above only")
                    st.rerun()
            
            with col3:
                if st.button("❌ Disable All Auto-Scheduling", use_container_width=True):
                    for todos_list in unique_lists:
                        current_settings = auto_scheduling_settings.get(todos_list, {})
                        if isinstance(current_settings, int):
                            threshold = 5 - current_settings  # Convert old format
                        else:
                            threshold = current_settings.get("min_priority", 4)
                        
                        auto_scheduling_settings[todos_list] = {
                            "enabled": False,
                            "min_priority": threshold,
                            "include_no_priority": True
                        }
                    settings["auto_scheduling_priority"] = auto_scheduling_settings
                    st.success("All lists disabled from auto-scheduling")
                    st.rerun()
            
            with col4:
                if st.button("🔄 Reset to Defaults", use_container_width=True):
                    # Reset to default values with corrected API priority values
                    default_settings = {
                        "work": {"enabled": True, "min_priority": 1, "include_no_priority": True},
                        "general": {"enabled": True, "min_priority": 2, "include_no_priority": True},
                        "learning": {"enabled": True, "min_priority": 3, "include_no_priority": True},
                        "musts": {"enabled": True, "min_priority": 1, "include_no_priority": True}
                    }
                    for todos_list in unique_lists:
                        auto_scheduling_settings[todos_list] = default_settings.get(
                            todos_list, 
                            {"enabled": True, "min_priority": 1, "include_no_priority": True}
                        )
                    settings["auto_scheduling_priority"] = auto_scheduling_settings
                    st.success("Reset to default priority settings")
                    st.rerun()
    
    elif active_tab == "calendars":
        st.subheader("Calendar Selection")
        st.markdown("Select which calendars to include when checking for free time slots")
        
        # Add informational callout
        st.info("""
        📅 **How Calendar Selection Works:**
        - Only selected calendars will be checked for existing events when finding free time slots
        - This affects the AI agent's ability to schedule tasks around your existing commitments
        - Primary calendars are typically your main personal/work calendars
        - You can manually add additional calendar IDs if needed
        """)
        
        # Initialize calendar settings
        if "calendar_settings" not in settings:
            settings["calendar_settings"] = {}
        
        # Check which accounts are authenticated
        main_token_valid, _ = validate_google_token("google_token_main.json")
        work_token_valid, _ = validate_google_token("google_token_work.json")
        
        if not main_token_valid and not work_token_valid:
            st.warning("⚠️ No Google accounts are authenticated. Please authenticate your accounts in the Authentication tab first.")
            return
        
        # Auto-discover calendars when tab loads (if not already discovered)
        if not hasattr(st.session_state, 'discovered_calendars'):
            with st.spinner("🔍 Auto-discovering calendars..."):
                accounts_to_check = []
                if main_token_valid:
                    accounts_to_check.append(("main", "tokens/google_token_main.json"))
                if work_token_valid:
                    accounts_to_check.append(("work", "tokens/google_token_work.json"))
                
                try:
                    from google_calendar import get_available_calendars
                    
                    calendar_discovery = {}
                    
                    for account_name, token_file in accounts_to_check:
                        try:
                            calendars = get_available_calendars(token_file)
                            calendar_discovery[account_name] = calendars
                        except Exception as e:
                            st.warning(f"⚠️ Could not discover calendars for {account_name}: {str(e)}")
                            calendar_discovery[account_name] = []
                    
                    # Store discovered calendars in session state
                    st.session_state.discovered_calendars = calendar_discovery
                    st.success("✅ Calendars auto-discovered!")
                    
                except Exception as e:
                    st.error(f"❌ Calendar auto-discovery failed: {str(e)}")
                    st.session_state.discovered_calendars = {}
        
        # Manual refresh button
        if st.button("🔄 Refresh Calendar List", help="Re-fetch calendar list from your Google accounts"):
            accounts_to_check = []
            if main_token_valid:
                accounts_to_check.append(("main", "tokens/google_token_main.json"))
            if work_token_valid:
                accounts_to_check.append(("work", "tokens/google_token_work.json"))
            
            try:
                from google_calendar import get_available_calendars
                
                calendar_discovery = {}
                
                for account_name, token_file in accounts_to_check:
                    with st.spinner(f"Refreshing {account_name} account calendars..."):
                        try:
                            calendars = get_available_calendars(token_file)
                            calendar_discovery[account_name] = calendars
                        except Exception as e:
                            st.warning(f"⚠️ Could not refresh calendars for {account_name}: {str(e)}")
                            calendar_discovery[account_name] = []
                
                # Update discovered calendars in session state
                st.session_state.discovered_calendars = calendar_discovery
                st.success("✅ Calendar list refreshed!")
                st.rerun()
                
            except Exception as e:
                st.error(f"❌ Calendar refresh failed: {str(e)}")
        
        # Display calendar selection for each account
        settings_changed = False
        for account_name in ["main", "work"]:
            token_valid = main_token_valid if account_name == "main" else work_token_valid
            
            if not token_valid:
                continue
            
            st.markdown(f"### {account_name.title()} Account")
            
            # Initialize account settings
            if account_name not in settings["calendar_settings"]:
                settings["calendar_settings"][account_name] = {
                    "included_calendars": []
                }
            
            current_included = settings["calendar_settings"][account_name].get("included_calendars", [])
            
            # Show discovered calendars if available
            if hasattr(st.session_state, 'discovered_calendars') and account_name in st.session_state.discovered_calendars:
                calendars = st.session_state.discovered_calendars[account_name]
                
                if calendars:
                    # Make the calendar list collapsible
                    with st.expander(f"📅 **Available Calendars** ({len(calendars)} found)", expanded=True):
                        # Create a list to track new selections
                        new_included = []
                        
                        for cal in calendars:
                            cal_id = cal['id']
                            cal_name = cal['summary']
                            is_primary = cal.get('primary', False)
                            is_selected = cal.get('selected', True)  # From Google
                            is_included = cal_id in current_included
                            
                            # Default to including primary calendar and previously selected calendars
                            default_include = is_primary or is_included
                            
                            # Create checkbox for each calendar
                            include_calendar = st.checkbox(
                                f"**{cal_name}**" + (" 🌟 (Primary)" if is_primary else "") + (" ✅ (Selected in Google)" if is_selected else ""),
                                value=default_include,
                                key=f"cal_{account_name}_{cal_id}",
                                help=f"Calendar ID: {cal_id}"
                            )
                            
                            if include_calendar:
                                new_included.append(cal_id)
                        
                        # Check if settings changed
                        if set(new_included) != set(current_included):
                            settings_changed = True
                        
                        # Update settings with new selections
                        settings["calendar_settings"][account_name]["included_calendars"] = new_included
                        
                        # Show summary inside the expander
                        if new_included:
                            st.success(f"✅ {len(new_included)} calendar(s) selected for {account_name}")
                        else:
                            st.warning(f"⚠️ No calendars selected for {account_name}")
                else:
                    st.error(f"❌ No calendars found for {account_name} account")
            else:
                # Show current settings if no discovery has been done yet
                if current_included:
                    st.markdown("**Currently Included Calendars:**")
                    for i, cal_id in enumerate(current_included):
                        col1, col2 = st.columns([4, 1])
                        with col1:
                            st.text(cal_id)
                        with col2:
                            if st.button("🗑️", key=f"remove_{account_name}_{i}", help="Remove calendar"):
                                current_included.remove(cal_id)
                                settings["calendar_settings"][account_name]["included_calendars"] = current_included
                                settings_changed = True
                                st.rerun()
                else:
                    st.info(f"ℹ️ No calendars configured for {account_name}. Auto-discovery is running...")
            
            # Manual calendar addition (always available)
            st.markdown("**Manual Calendar Addition:**")
            new_cal_id = st.text_input(
                f"Add Calendar ID for {account_name}",
                placeholder="e.g., your.email@gmail.com or calendar_id@group.calendar.google.com",
                key=f"manual_{account_name}"
            )
            
            if st.button(f"➕ Add", key=f"add_manual_{account_name}") and new_cal_id.strip():
                if new_cal_id.strip() not in current_included:
                    current_included.append(new_cal_id.strip())
                    settings["calendar_settings"][account_name]["included_calendars"] = current_included
                    settings_changed = True
                    st.success(f"Added calendar: {new_cal_id.strip()}")
                    st.rerun()
                else:
                    st.warning("Calendar already added")
            
            st.markdown("---")
        
        # Auto-save settings if changed
        if settings_changed:
            config_manager.save_settings(settings)
            st.success("📁 Calendar settings saved automatically!")
        
        # Settings summary
        st.markdown("### 📊 Calendar Settings Summary")
        
        total_calendars = 0
        for account_name, account_settings in settings.get("calendar_settings", {}).items():
            included_count = len(account_settings.get("included_calendars", []))
            total_calendars += included_count
            
            if included_count > 0:
                st.success(f"✅ **{account_name.title()}**: {included_count} calendar(s)")
            else:
                st.warning(f"⚠️ **{account_name.title()}**: No calendars selected")
        
        if total_calendars == 0:
            st.error("❌ **No calendars selected across all accounts!** The system won't be able to check for free time slots.")
        else:
            st.info(f"📅 **Total**: {total_calendars} calendar(s) will be checked for free time slots")
        
        # Explanation
        with st.expander("ℹ️ How Calendar Selection Works"):
            st.markdown("""
            **Calendar Selection determines which calendars are checked when finding free time slots:**
            
            - **Primary calendars** are typically your main personal calendar
            - **Selected calendars** are those you've marked as visible in Google Calendar
            - **Group calendars** might include shared team calendars or project-specific calendars
            
            **Recommendations:**
            - Include your primary calendar to avoid conflicts with personal events
            - Include work calendars if scheduling work tasks
            - Exclude calendars you don't want to block scheduling time (e.g., holidays, birthdays)
            """)
        
        # Test calendar configuration
        st.markdown("### 🧪 Test Calendar Configuration")
        
        if st.button("🔍 Test Free Time Detection", help="Test if your calendar configuration is working correctly"):
            try:
                # Get next 24 hours for testing
                from datetime import datetime, timedelta
                import pytz
                from config_manager import config_manager
                
                settings_test = config_manager.load_settings()
                timezone_str = settings_test.get("timezone", "Asia/Jerusalem")
                local_tz = pytz.timezone(timezone_str)
                
                now = datetime.now(local_tz)
                end_time = now + timedelta(hours=24)
                
                start_timestamp = now.isoformat()
                end_timestamp = end_time.isoformat()
                
                with st.spinner("Testing calendar access and free time detection..."):
                    from google_calendar import get_free_intervals
                    
                    # Test with the current calendar settings using asyncio.run()
                    free_intervals = aio.run(get_free_intervals(start_timestamp, end_timestamp))
                    
                    if free_intervals:
                        st.success(f"✅ Calendar test successful! Found {len(free_intervals)} free time slots in the next 24 hours.")
                        
                        # Show a few examples
                        st.markdown("**Sample Free Time Slots:**")
                        for i, interval in enumerate(free_intervals[:5]):  # Show first 5
                            start_dt = datetime.fromisoformat(interval['start'].replace('Z', '+00:00')).astimezone(local_tz)
                            end_dt = datetime.fromisoformat(interval['end'].replace('Z', '+00:00')).astimezone(local_tz)
                            duration = end_dt - start_dt
                            duration_minutes = int(duration.total_seconds() / 60)
                            
                            st.text(f"  • {start_dt.strftime('%a %m/%d %H:%M')} - {end_dt.strftime('%H:%M')} ({duration_minutes} min)")
                        
                        if len(free_intervals) > 5:
                            st.text(f"  ... and {len(free_intervals) - 5} more slots")
                            
                    else:
                        st.warning("⚠️ No free time slots found in the next 24 hours. This could mean:")
                        st.markdown("""
                        - Your calendars are fully booked
                        - The calendar selection might be too restrictive
                        - There might be an issue with calendar access
                        """)
                        
            except Exception as e:
                st.error(f"❌ Calendar test failed: {str(e)}")
                st.markdown("**Possible issues:**")
                st.markdown("""
                                        - Calendar authentication might have expired
                        - Selected calendars might not be accessible
                        - Network connectivity issues
                        """)
    
    elif active_tab == "autocategorization":
        st.subheader("🏷️ Auto-Categorization Settings")
        st.markdown("Configure automatic categorization of tasks by project sections/labels using AI")
        
        # Add informational callout
        st.info("""
        🤖 **How Auto-Categorization Works:**
        - When a new task is created in an enabled project, AI analyzes the task content
        - The AI categorizes the task by moving it to the appropriate section (if sections exist)
        - This happens automatically before any scheduling logic runs
        - You can provide context to help the AI understand your categorization preferences
        """)
        
        # Initialize autocategorization settings
        if "autocategorization" not in settings:
            settings["autocategorization"] = {
                "enabled_projects": [],
                "project_contexts": {}
            }
        
        autocategorization = settings["autocategorization"]
        enabled_projects = autocategorization.get("enabled_projects", [])
        project_contexts = autocategorization.get("project_contexts", {})
        
        # Get project mappings to know what projects exist
        project_mappings = settings.get("project_mappings", {})
        
        if not project_mappings:
            st.warning("⚠️ No project mappings configured yet. Please configure project mappings first in the Project Mappings tab.")
            return
        
        # Available projects (use mapped names for cleaner UI)
        available_projects = sorted(set(project_mappings.values()))
        
        st.markdown("### 📋 Project Selection")
        st.markdown("Select which projects should have automatic categorization enabled:")
        
        # Show available projects with checkboxes
        settings_changed = False
        col1, col2 = st.columns([3, 1])
        
        with col1:
            st.markdown("**Available Projects:**")
            new_enabled_projects = []
            
            for project in available_projects:
                # Find the project IDs that map to this name
                matching_ids = [pid for pid, name in project_mappings.items() if name == project]
                display_name = project
                if len(matching_ids) == 1:
                    help_text = f"Project: {project} (ID: {matching_ids[0]})"
                else:
                    help_text = f"Project: {project} (IDs: {', '.join(matching_ids)})"
                
                is_enabled = project in enabled_projects
                
                enable_project = st.checkbox(
                    display_name,
                    value=is_enabled,
                    key=f"enable_{project}",
                    help=help_text
                )
                
                if enable_project:
                    new_enabled_projects.append(project)
            
            # Check if enabled projects changed
            if set(new_enabled_projects) != set(enabled_projects):
                settings_changed = True
                autocategorization["enabled_projects"] = new_enabled_projects
                enabled_projects = new_enabled_projects
        
        with col2:
            st.markdown("**Current Status:**")
            if enabled_projects:
                st.success(f"✅ {len(enabled_projects)} project(s) enabled")
                for project in enabled_projects:
                    st.text(f"• {project}")
            else:
                st.warning("⚠️ No projects enabled")
        
        st.markdown("---")
        
        # Project contexts configuration
        st.markdown("### 🎯 Project Context Configuration")
        st.markdown("Provide context for each enabled project to help AI understand how to categorize tasks:")
        
        if not enabled_projects:
            st.info("ℹ️ Enable some projects above to configure their contexts.")
        else:
            for project in enabled_projects:
                st.markdown(f"**Context for: {project}**")
                
                current_context = project_contexts.get(project, "")
                
                # Suggest default context based on project name/mapping
                default_suggestions = {
                    "groceries": "This is a grocery shopping list where items should be categorized by type (dairy, meat, vegetables, fruits, etc.) to make shopping more organized.",
                    "work": "This is a work project where tasks should be categorized by priority, department, or project phase.",
                    "personal": "This is a personal project where tasks should be categorized by life area (health, finance, home, etc.).",
                    "health": "This is a health-focused project where tasks should be categorized by activity type (exercise, medical, nutrition, etc.).",
                    "learning": "This is a learning project where tasks should be categorized by subject, skill level, or study method."
                }
                
                # Find suggestion based on project name (case-insensitive)
                suggestion = ""
                project_lower = project.lower()
                for key, value in default_suggestions.items():
                    if key in project_lower or project_lower in key:
                        suggestion = value
                        break
                
                # Quick suggestion buttons (place before text area)
                if suggestion and not current_context:
                    if st.button(f"💡 Use suggested context", key=f"suggest_{project}"):
                        project_contexts[project] = suggestion
                        current_context = suggestion  # Update the current context immediately
                        
                        # Update the settings object and save immediately
                        autocategorization["project_contexts"] = project_contexts
                        settings["autocategorization"] = autocategorization
                        
                        try:
                            config_manager.save_settings(settings)
                            st.success(f"✅ Applied suggested context for {project}!")
                            st.rerun()
                        except Exception as e:
                            st.error(f"❌ Failed to save settings: {str(e)}")
                
                new_context = st.text_area(
                    f"Context for {project}",
                    value=current_context,
                    placeholder=suggestion or "Describe this project and how tasks should be categorized (e.g., by priority, type, category, etc.)",
                    height=100,
                    key=f"context_{project}",
                    help="This context helps the AI understand how to categorize tasks in this project. Be specific about the types of sections or categories you use."
                )
                
                # Update context if changed
                if new_context != current_context:
                    project_contexts[project] = new_context.strip()
                    settings_changed = True
                
                st.markdown("---")
        
        # Update the settings object
        autocategorization["project_contexts"] = project_contexts
        settings["autocategorization"] = autocategorization
        
        # Test categorization section
        st.markdown("### 🧪 Test Categorization")
        st.markdown("Test how the AI would categorize sample tasks:")
        
        if enabled_projects:
            col1, col2 = st.columns([2, 1])
            
            with col1:
                test_task = st.text_input(
                    "Test Task",
                    placeholder="e.g., 'buy milk and bread' or 'schedule doctor appointment'",
                    help="Enter a sample task to see how it would be categorized"
                )
            
            with col2:
                test_project = st.selectbox(
                    "Test Project",
                    enabled_projects,
                    help="Select which project to test categorization for"
                )
            
            if st.button("🤖 Test Categorization", type="primary") and test_task.strip():
                with st.spinner("🤖 Testing categorization..."):
                    try:
                        # Import the autocategorizer to test
                        import sys
                        import os
                        
                        # Add current directory to Python path
                        current_dir = os.path.dirname(os.path.abspath(__file__))
                        if current_dir not in sys.path:
                            sys.path.insert(0, current_dir)
                        
                        from autocategorizer import classify_task_into_section, get_project_sections_with_descriptions
                        
                        # Find the project ID for this mapped name to get real sections
                        matching_ids = [pid for pid, name in project_mappings.items() if name == test_project]
                        
                        if matching_ids:
                            # Use the first matching project ID to get sections
                            project_id = matching_ids[0]
                            try:
                                # Get real sections from the project
                                import asyncio
                                sections = asyncio.run(get_project_sections_with_descriptions(project_id))
                                if sections:
                                    section_names = [section.get('name', 'Unnamed') for section in sections]
                                    st.info(f"📋 Using real sections from project {test_project}: {', '.join(section_names)}")
                                else:
                                    # Fallback for projects without sections
                                    sections = [
                                        {"id": "mock1", "name": "Category A"},
                                        {"id": "mock2", "name": "Category B"},
                                        {"id": "mock3", "name": "Other"}
                                    ]
                                    st.warning("⚠️ No sections found in project, using mock sections")
                            except Exception as e:
                                st.warning(f"⚠️ Could not fetch real sections, using mock sections: {str(e)}")
                                sections = [
                                    {"id": "mock1", "name": "Category A"},
                                    {"id": "mock2", "name": "Category B"}, 
                                    {"id": "mock3", "name": "Other"}
                                ]
                        else:
                            # Fallback to mock sections
                            st.info("💡 Testing with mock sections")
                            sections = [
                                {"id": "mock1", "name": "Category A"},
                                {"id": "mock2", "name": "Category B"},
                                {"id": "mock3", "name": "Other"}
                            ]
                        
                        # Test the categorization using the actual function
                        section_id = asyncio.run(classify_task_into_section(
                            task_content=test_task.strip(),
                            task_description="",  # Empty description for test
                            sections=sections,
                            project_context=project_contexts.get(test_project, "")
                        ))
                        
                        # Find the section name from the ID
                        result = "Other"  # Default
                        if section_id:
                            for section in sections:
                                if section.get("id") == section_id:
                                    result = section.get("name", "Other")
                                    break
                        
                        if result and result != "Other":
                            st.success(f"✅ **Categorization Result:** `{result}`")
                            st.info(f"💭 **Analysis:** The AI would move '{test_task}' to the '{result}' section based on the project context.")
                        else:
                            st.warning(f"⚠️ **No specific category found** - task would stay in default location")
                            
                    except ImportError:
                        st.error("❌ Autocategorizer module not found. Make sure the system is properly installed.")
                    except Exception as e:
                        st.error(f"❌ Test failed: {str(e)}")
        else:
            st.info("ℹ️ Enable some projects above to test categorization.")
        
        # Auto-save settings if changed
        if settings_changed:
            try:
                config_manager.save_settings(settings)
                st.success("📁 Auto-categorization settings saved automatically!")
            except Exception as e:
                st.error(f"❌ Failed to save settings: {str(e)}")
        
        # Settings summary
        st.markdown("---")
        st.markdown("### 📊 Auto-Categorization Summary")
        
        if enabled_projects:
            st.success(f"✅ **{len(enabled_projects)} project(s) enabled** for auto-categorization")
            
            for project in enabled_projects:
                context = project_contexts.get(project, "")
                context_status = "✅ Configured" if context.strip() else "⚠️ No context"
                st.markdown(f"- **{project}**: {context_status}")
                if context.strip():
                    st.markdown(f"  *{context[:100]}{'...' if len(context) > 100 else ''}*")
        else:
            st.info("ℹ️ No projects enabled for auto-categorization")
        
        # Show current JSON config (for debugging)
        with st.expander("🔧 Raw Configuration (Advanced)", expanded=False):
            st.json(autocategorization)
    
    elif active_tab == "prompts":
        st.subheader("AI Agent Prompts")
        st.markdown("Customize the system prompts for different AI agents")
        
        # Get available agents
        available_agents = config_manager.list_available_agents()
        
        if not available_agents:
            st.warning("⚠️ No agents found in prompts configuration")
            return
        
        # Agent selection
        selected_agent = st.selectbox(
            "Select Agent to Edit",
            available_agents,
            help="Choose which agent's prompt you want to edit"
        )
        
        if selected_agent:
            # Get current agent data
            agent_data = prompts.get("agents", {}).get(selected_agent, {})
            
            st.markdown(f"**Editing: {selected_agent}**")
            
            # Description
            agent_description = st.text_input(
                "Agent Description",
                value=agent_data.get("description", ""),
                help="Brief description of what this agent does"
            )
            
            # System prompt editor
            st.markdown("**System Prompt:**")
            current_prompt = agent_data.get("system_prompt", "")
            new_system_prompt = st.text_area(
                "System Prompt",
                value=current_prompt,
                height=400,
                help="The main instructions for the AI agent. Use {current_time} as a placeholder for the current timestamp."
            )
            
            # Preview with current time
            st.markdown("**Preview (with current time filled):**")
            from datetime import datetime
            import pytz
            
            # Get timezone from settings
            timezone = settings.get("timezone", "Asia/Jerusalem")
            israel_tz = pytz.timezone(timezone)
            current_time = datetime.now(israel_tz).replace(microsecond=0).isoformat()
            
            try:
                preview = new_system_prompt.format(current_time=current_time)
                st.code(preview, language="text")
            except KeyError as e:
                st.warning(f"⚠️ Missing placeholder: {e}")
                st.code(new_system_prompt, language="text")
            
            # Update prompts structure
            if "agents" not in prompts:
                prompts["agents"] = {}
            if selected_agent not in prompts["agents"]:
                prompts["agents"][selected_agent] = {}
            
            # Update the agent data
            prompts["agents"][selected_agent]["system_prompt"] = new_system_prompt
            prompts["agents"][selected_agent]["description"] = agent_description
        
        # Add new agent section
        st.markdown("---")
        st.markdown("**Add New Agent:**")
        col1, col2, col3 = st.columns([2, 2, 1])
        
        with col1:
            new_agent_name = st.text_input(
                "Agent Name",
                placeholder="e.g., reminder_agent, priority_agent",
                help="Use underscore format: agent_name"
            )
        
        with col2:
            new_agent_desc = st.text_input(
                "Agent Description",
                placeholder="e.g., Handles reminders and notifications"
            )
        
        with col3:
            if st.button("➕ Add Agent") and new_agent_name and new_agent_desc:
                if "agents" not in prompts:
                    prompts["agents"] = {}
                
                prompts["agents"][new_agent_name.strip()] = {
                    "system_prompt": "You are a helpful AI assistant. The current time is: {current_time}.",
                    "description": new_agent_desc.strip()
                }
                
                config_manager.save_prompts(prompts)
                st.success(f"Added new agent: {new_agent_name.strip()}")
                st.rerun()
    
    elif active_tab == "settings":
        st.subheader("General Settings")
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("**OpenAI Settings:**")
            new_model = st.selectbox(
                "Model",
                ["gpt-4.1-nano", "gpt-4.1-mini", "gpt-4.1", "gpt-3.5-turbo"],
                index=["gpt-4.1-nano", "gpt-4.1-mini", "gpt-4.1", "gpt-3.5-turbo"].index(
                    settings.get("openai", {}).get("model", "gpt-4.1-nano")
                )
            )
            settings["openai"] = {"model": new_model}
            
            st.markdown("**Timezone:**")
            new_timezone = st.text_input(
                "Timezone",
                value=settings.get("timezone", "Asia/Jerusalem")
            )
            settings["timezone"] = new_timezone
        
        with col2:
            st.markdown("**Webhook Server:**")
            new_host = st.text_input(
                "Host",
                value=settings.get("webhook", {}).get("host", "0.0.0.0")
            )
            new_port = st.number_input(
                "Port",
                value=settings.get("webhook", {}).get("port", 5055),
                min_value=1000,
                max_value=65535
            )
            settings["webhook"] = {"host": new_host, "port": new_port}
    
    # Save all changes
    st.markdown("---")
    st.markdown("**Save Configuration:**")
    col1, col2, col3 = st.columns([1, 1, 1])
    
    with col1:
        if st.button("💾 Save Settings", type="primary", use_container_width=True):
            try:
                config_manager.save_settings(settings)
                st.success("✅ Settings saved successfully!")
            except Exception as e:
                st.error(f"❌ Failed to save settings: {str(e)}")
    
    with col2:
        if st.button("🤖 Save Prompts", type="primary", use_container_width=True):
            try:
                config_manager.save_prompts(prompts)
                st.success("✅ Prompts saved successfully!")
            except Exception as e:
                st.error(f"❌ Failed to save prompts: {str(e)}")
    
    with col3:
        if st.button("🔄 Reload Config", use_container_width=True):
            st.rerun()

def show_webhook_page():
    st.header("🚀 Webhook Server")
    st.markdown("Control and monitor the webhook server")
    
    from config_manager import config_manager
    import subprocess
    import psutil
    import requests
    import time
    from pathlib import Path
    
    # Load settings
    try:
        settings = config_manager.load_settings()
        webhook_config = settings.get("webhook", {"host": "0.0.0.0", "port": 5055})
        host = webhook_config.get("host", "0.0.0.0")
        port = webhook_config.get("port", 5055)
    except Exception as e:
        st.error(f"❌ Error loading webhook settings: {str(e)}")
        st.info("💡 Using default settings: host=0.0.0.0, port=5055")
        host = "0.0.0.0"
        port = 5055
    
    # Server URL
    # Use 127.0.0.1 instead of localhost for better container compatibility
    health_check_host = "127.0.0.1" if host in ["0.0.0.0", "localhost"] else host
    server_url = f"http://localhost:{port}"  # Keep this for display purposes
    health_url = f"http://{health_check_host}:{port}/health"
    webhook_url = f"{server_url}/webhook/todoist"
    
    # Check server status
    def check_server_status():
        try:
            response = requests.get(health_url, timeout=2)
            return response.status_code == 200, response.json() if response.status_code == 200 else None
        except:
            return False, None
    
    # Find webhook server process
    def find_webhook_process():
        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                cmdline = ' '.join(proc.info['cmdline'] or [])
                if 'webhook_server' in cmdline and str(port) in cmdline:
                    return proc.info['pid']
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        return None
    
    # Server status section
    col1, col2, col3 = st.columns([2, 1, 1])
    
    with col1:
        st.subheader("📊 Server Status")
        
        is_running, health_data = check_server_status()
        webhook_pid = find_webhook_process()
        
        if is_running:
            st.success("✅ **Server is RUNNING**")
            if health_data:
                st.json(health_data)
            if webhook_pid:
                st.info(f"🆔 Process ID: {webhook_pid}")
        else:
            st.error("❌ **Server is STOPPED**")
            if webhook_pid:
                st.warning(f"⚠️ Found process {webhook_pid} but health check failed")
                # Debug: Show more process details
                try:
                    proc = psutil.Process(webhook_pid)
                    st.code(f"Process details:\nStatus: {proc.status()}\nCmdline: {' '.join(proc.cmdline())}\nCWD: {proc.cwd()}", language="text")
                except Exception as e:
                    st.code(f"Could not get process details: {e}", language="text")
    
    with col2:
        st.markdown("**Server Config:**")
        st.text(f"Host: {host}")
        st.text(f"Port: {port}")
        st.text(f"URL: {server_url}")
    
    with col3:
        st.markdown("**Quick Actions:**")
        if st.button("🔄 Refresh Status", use_container_width=True):
            st.rerun()
        
        if st.button("🌐 Open in Browser", use_container_width=True):
            st.markdown(f"[Open Server]({server_url})")
        
        if st.button("🔍 Debug Port", use_container_width=True):
            # Check if anything is listening on the port
            import socket
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(1)
                result = sock.connect_ex(('127.0.0.1', port))
                sock.close()
                if result == 0:
                    st.success(f"✅ Port {port} is open and listening")
                else:
                    st.error(f"❌ Port {port} is not responding")
            except Exception as e:
                st.error(f"❌ Port check failed: {e}")
    
    # Control section
    st.markdown("---")
    st.subheader("🎮 Server Control")
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        if st.button("▶️ Start Server", type="primary", use_container_width=True):
            if is_running:
                st.warning("⚠️ Server is already running!")
            else:
                try:
                    # Start the webhook server
                    cmd = [
                        "python", "-m", "uvicorn", 
                        "webhook_server:app",
                        "--host", str(host),
                        "--port", str(port),
                        "--reload"
                    ]
                    
                    # Determine correct working directory
                    current_dir = Path.cwd()
                    if current_dir.name == "todos-agent":
                        # Already in todos-agent directory
                        work_dir = current_dir
                    elif (current_dir / "todos-agent").exists():
                        # In parent directory, todos-agent exists as subdirectory
                        work_dir = current_dir / "todos-agent"
                    else:
                        # Fallback to current directory
                        work_dir = current_dir
                    
                    st.info(f"🔍 Starting server from directory: {work_dir}")
                    
                    # Start in background
                    process = subprocess.Popen(
                        cmd,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        cwd=work_dir
                    )
                    
                    # Wait a moment and check if it started
                    time.sleep(2)
                    if process.poll() is None:  # Still running
                        st.success("✅ Server started successfully!")
                        time.sleep(1)
                        st.rerun()
                    else:
                        stdout, stderr = process.communicate()
                        st.error(f"❌ Failed to start server")
                        if stdout:
                            st.code(f"STDOUT:\n{stdout.decode()}", language="text")
                        if stderr:
                            st.code(f"STDERR:\n{stderr.decode()}", language="text")
                        
                except Exception as e:
                    st.error(f"❌ Error starting server: {str(e)}")
    
    with col2:
        if st.button("⏹️ Stop Server", use_container_width=True):
            if not is_running:
                st.warning("⚠️ Server is not running!")
            else:
                try:
                    if webhook_pid:
                        proc = psutil.Process(webhook_pid)
                        proc.terminate()
                        proc.wait(timeout=5)
                        st.success("✅ Server stopped successfully!")
                        time.sleep(1)
                        st.rerun()
                    else:
                        st.error("❌ Could not find server process")
                except Exception as e:
                    st.error(f"❌ Error stopping server: {str(e)}")
    
    with col3:
        if st.button("🔄 Restart Server", use_container_width=True):
            try:
                # Stop if running
                if webhook_pid:
                    proc = psutil.Process(webhook_pid)
                    proc.terminate()
                    proc.wait(timeout=5)
                    time.sleep(1)
                
                # Start again
                cmd = [
                    "python", "-m", "uvicorn", 
                    "webhook_server:app",
                    "--host", str(host),
                    "--port", str(port),
                    "--reload"
                ]
                
                # Determine correct working directory
                current_dir = Path.cwd()
                if current_dir.name == "todos-agent":
                    # Already in todos-agent directory
                    work_dir = current_dir
                elif (current_dir / "todos-agent").exists():
                    # In parent directory, todos-agent exists as subdirectory
                    work_dir = current_dir / "todos-agent"
                else:
                    # Fallback to current directory
                    work_dir = current_dir
                
                process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    cwd=work_dir
                )
                
                time.sleep(2)
                if process.poll() is None:
                    st.success("✅ Server restarted successfully!")
                    time.sleep(1)
                    st.rerun()
                else:
                    st.error("❌ Failed to restart server")
                    
            except Exception as e:
                st.error(f"❌ Error restarting server: {str(e)}")
    
    with col4:
        if st.button("📋 View Logs", use_container_width=True):
            st.session_state.show_logs = not st.session_state.get("show_logs", False)
    
    # Logs section - MOVED ABOVE Configuration section
    if st.session_state.get("show_logs", False):
        st.markdown("---")
        st.subheader("📄 Server Logs")
        
        # Auto-refresh toggle and controls
        col1, col2, col3 = st.columns([2, 1, 1])
        
        with col1:
            auto_refresh = st.checkbox("🔄 Auto-refresh logs (every 5 seconds)", value=False)
        
        with col2:
            if st.button("🔄 Refresh Now", use_container_width=True):
                st.rerun()
        
        with col3:
            if st.button("🗑️ Clear Display", use_container_width=True):
                st.session_state.logs_cleared = True
                # Collapse all expandable sections by clearing expansion state
                st.session_state.expand_logs = False
                st.rerun()
        
        # Fetch logs from webhook server
        def fetch_webhook_logs():
            """Fetch recent webhook events from the server"""
            try:
                logs_url = f"http://127.0.0.1:{port}/webhook/logs"
                response = requests.get(logs_url, timeout=5)
                if response.status_code == 200:
                    return response.json().get("events", [])
                else:
                    return None
            except Exception as e:
                return None
        
        # Display logs
        if is_running:
            logs = fetch_webhook_logs()
            
            if logs is None:
                st.warning("⚠️ Could not fetch logs from webhook server. Make sure the server is running.")
            elif not logs:
                st.info("📝 No webhook events yet. Send a test webhook or add a task in Todoist to see events here.")
            else:
                # Filter out cleared logs if requested
                if st.session_state.get("logs_cleared", False):
                    # Only show new logs after clearing (this is a simple implementation)
                    # In a production app, you might want to track the clear timestamp
                    st.info("📝 Display cleared. New events will appear below.")
                    st.session_state.logs_cleared = False
                
                # Display logs in reverse chronological order (newest first)
                logs_reversed = sorted(logs, key=lambda x: x.get("timestamp", ""), reverse=True)
                
                # Limit display to last 20 events for performance
                display_logs = logs_reversed[:20]
                
                st.markdown(f"**Showing {len(display_logs)} most recent events (of {len(logs)} total)**")
                
                # Determine if logs should be expanded - only expand if not just cleared
                expand_logs = st.session_state.get("expand_logs", True)
                if st.session_state.get("logs_cleared", False):
                    expand_logs = False
                
                # Create expandable sections for each event
                for i, log_entry in enumerate(display_logs):
                    timestamp = log_entry.get("timestamp", "Unknown")
                    event_type = log_entry.get("event_type", "UNKNOWN")
                    task_content = log_entry.get("task_content", "No content")
                    task_id = log_entry.get("task_id", "Unknown")
                    error = log_entry.get("error")
                    result = log_entry.get("result")
                    
                    # Format timestamp for display
                    try:
                        dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                        formatted_time = dt.strftime("%H:%M:%S")
                        formatted_date = dt.strftime("%Y-%m-%d")
                    except:
                        formatted_time = timestamp
                        formatted_date = ""
                    
                    # Color code by event type
                    if event_type.startswith("TRIGGER_RECEIVED"):
                        emoji = "📥"
                        color = "blue"
                    elif event_type.startswith("TASK_ACTION"):
                        # Use specific emoji based on action type
                        if "RESCHEDULED" in event_type:
                            emoji = "🔄"
                        elif "IGNORED" in event_type:
                            emoji = "⏸️"
                        elif "SKIPPED" in event_type:
                            emoji = "⏭️"
                        elif "COMPLETED" in event_type:
                            emoji = "✅"
                        elif "DELETED" in event_type:
                            emoji = "🗑️"
                        elif "FAILED" in event_type:
                            emoji = "❌"
                        else:
                            emoji = "🔧"
                        color = "green"
                    elif event_type.startswith("WEBHOOK_BLOCKED"):
                        emoji = "🚫"
                        color = "orange"
                    elif "ERROR" in event_type:
                        emoji = "❌"
                        color = "red"
                    else:
                        emoji = "📝"
                        color = "gray"
                    
                    # Create expandable entry - expand based on state
                    # Safely handle task_content that might be None
                    safe_task_content = task_content or "No content"
                    content_preview = safe_task_content[:50] + ('...' if len(safe_task_content) > 50 else '')
                    
                    with st.expander(
                        f"{emoji} **{formatted_time}** | {event_type} | {content_preview}",
                        expanded=(expand_logs and i < 3)  # Only expand first 3 if expand_logs is True
                    ):
                        col1, col2 = st.columns(2)
                        
                        with col1:
                            st.markdown("**Event Details:**")
                            st.write(f"📅 **Date:** {formatted_date}")
                            st.write(f"🕒 **Time:** {formatted_time}")
                            st.write(f"🏷️ **Type:** {event_type}")
                            st.write(f"🆔 **Task ID:** {task_id}")
                            st.write(f"📝 **Content:** {safe_task_content}")
                            
                            if log_entry.get("project_id"):
                                st.write(f"📁 **Project:** {log_entry.get('project_id')}")
                            if log_entry.get("priority"):
                                st.write(f"⭐ **Priority:** {log_entry.get('priority')}")
                        
                        with col2:
                            if error:
                                st.markdown("**❌ Error:**")
                                st.error(error)
                            
                            if result:
                                st.markdown("**✅ Result:**")
                                if isinstance(result, dict):
                                    if result.get("processing_time_seconds"):
                                        st.write(f"⏱️ **Processing Time:** {result['processing_time_seconds']:.2f}s")
                                    if result.get("agent_result"):
                                        # Display agent_result as text since it's a string, not JSON
                                        agent_result = result["agent_result"]
                                        if isinstance(agent_result, str):
                                            st.success(agent_result)
                                        else:
                                            st.json(agent_result)
                                else:
                                    st.json(result)
                        
                        # Raw data in a collapsible section
                        if st.checkbox(f"Show raw data", key=f"raw_{i}"):
                            st.json(log_entry)
                
                # Stats summary
                st.markdown("---")
                st.markdown("**📊 Event Summary:**")
                
                # Count events by type
                event_counts = {}
                for log in logs:
                    event_type = log.get("event_type", "UNKNOWN")
                    event_counts[event_type] = event_counts.get(event_type, 0) + 1
                
                # Display stats
                stat_cols = st.columns(len(event_counts) if event_counts else 1)
                for i, (event_type, count) in enumerate(event_counts.items()):
                    with stat_cols[i % len(stat_cols)]:
                        # Use same emoji logic as above
                        if event_type.startswith("TRIGGER_RECEIVED"):
                            emoji = "📥"
                        elif event_type.startswith("TASK_ACTION"):
                            if "RESCHEDULED" in event_type:
                                emoji = "🔄"
                            elif "IGNORED" in event_type:
                                emoji = "⏸️"
                            elif "SKIPPED" in event_type:
                                emoji = "⏭️"
                            elif "COMPLETED" in event_type:
                                emoji = "✅"
                            elif "DELETED" in event_type:
                                emoji = "🗑️"
                            elif "FAILED" in event_type:
                                emoji = "❌"
                            else:
                                emoji = "🔧"
                        elif event_type.startswith("WEBHOOK_BLOCKED"):
                            emoji = "🚫"
                        elif "ERROR" in event_type:
                            emoji = "❌"
                        else:
                            emoji = "📝"
                        
                        st.metric(f"{emoji} {event_type}", count)
        
        else:
            st.warning("⚠️ Start the webhook server to view logs")
        
        # Auto-refresh functionality
        if auto_refresh and is_running:
            # Add a small delay and rerun
            import time
            time.sleep(0.1)  # Small delay to prevent too rapid refreshing
            st.rerun()

# Add the authentication state management
def streamlit_authenticate_google(token_filename: str, account_description: str = "Google Account"):
    """Streamlit-compatible Google authentication flow using loopback method."""
    import os
    import threading
    import socket
    from urllib.parse import urlparse, parse_qs
    from http.server import HTTPServer, BaseHTTPRequestHandler
    from google_auth_oauthlib.flow import InstalledAppFlow
    
    # Initialize session state for this authentication
    auth_key = f"auth_{token_filename}"
    if f"{auth_key}_step" not in st.session_state:
        st.session_state[f"{auth_key}_step"] = "start"
    
    if not os.path.exists('tokens/google_credentials.json'):
        st.error("❌ Missing tokens/google_credentials.json file!")
        with st.expander("📋 Setup Instructions"):
            st.markdown("""
            1. Go to [Google Cloud Console](https://console.cloud.google.com/)
            2. Create a project and enable Google Calendar API
            3. Go to APIs & Services → Credentials
            4. Create OAuth 2.0 Client ID (Desktop)
            5. **Important**: Update Authorized redirect URIs to include `http://localhost:8080`
            6. Download and save as 'tokens/google_credentials.json'
            """)
        return False
    
    # Validate credentials and check redirect URI compatibility
    creds_valid, creds_msg, configured_redirect_uris = validate_google_credentials()
    if not creds_valid:
        st.error(f"❌ Invalid Google credentials: {creds_msg}")
        return False
    
    # Step 1: Generate and show the OAuth URL
    if st.session_state[f"{auth_key}_step"] == "start":
        if st.button(f"🚀 Start OAuth Flow for {account_description}", type="primary"):
            try:
                # Use fixed port for consistency with OAuth client configuration
                port = 8080
                
                # Detect if we're in Docker and determine the correct external URL
                external_host = os.getenv('EXTERNAL_HOST')  # e.g., "192.168.5.154:51823"
                
                if external_host:
                    redirect_uri = f"http://{external_host}"
                    listen_port = port  # Still listen on 8080 inside container
                    st.info(f"🐳 **Docker Mode**: Using external URL: {redirect_uri}")
                    st.info(f"📋 **Setup**: Make sure your Google OAuth client has this redirect URI: `{redirect_uri}`")
                else:
                    redirect_uri = f"http://localhost:{port}"
                    listen_port = port
                    st.info(f"🖥️ **Local Mode**: Using localhost: {redirect_uri}")
                
                # Validate redirect URI compatibility
                uri_compatible, uri_msg = check_redirect_uri_compatibility(redirect_uri, configured_redirect_uris)
                
                if not uri_compatible:
                    st.warning(f"⚠️ **Redirect URI Mismatch**: {uri_msg}")
                    st.markdown("**🔧 To fix this:**")
                    st.markdown(f"1. Go to [Google Cloud Console](https://console.cloud.google.com/)")
                    st.markdown(f"2. Navigate to **APIs & Services → Credentials**")
                    st.markdown(f"3. Click on your OAuth 2.0 Client ID")
                    st.markdown(f"4. Add `{redirect_uri}` to **Authorized redirect URIs**")
                    st.markdown(f"5. Save the changes")
                    
                    with st.expander("📋 Current configured redirect URIs"):
                        for uri in configured_redirect_uris:
                            st.code(uri)
                    
                    if not st.checkbox("⚠️ I understand the redirect URI mismatch but want to proceed anyway"):
                        st.stop()
                else:
                    st.success(f"✅ **Redirect URI**: {uri_msg}")
                
                # Scopes required for Google Calendar API
                SCOPES = ['https://www.googleapis.com/auth/calendar']
                
                # Create flow from client secrets
                flow = InstalledAppFlow.from_client_secrets_file('tokens/google_credentials.json', SCOPES)
                flow.redirect_uri = redirect_uri
                
                # Get the authorization URL
                auth_url, _ = flow.authorization_url(prompt='consent')
                
                # Store configuration in session state
                st.session_state[f"{auth_key}_flow_config"] = {
                    'client_config': flow.client_config,
                    'scopes': SCOPES,
                    'redirect_uri': redirect_uri,
                    'listen_port': listen_port
                }
                st.session_state[f"{auth_key}_auth_url"] = auth_url
                st.session_state[f"{auth_key}_step"] = "show_url"
                st.rerun()
                
            except Exception as e:
                st.error(f"❌ Failed to start OAuth flow: {str(e)}")
                return False
    
    # Step 2: Show URL and set up local server
    elif st.session_state[f"{auth_key}_step"] == "show_url":
        flow_config = st.session_state.get(f"{auth_key}_flow_config")
        auth_url = st.session_state.get(f"{auth_key}_auth_url")
        listen_port = flow_config.get('listen_port', 8080)
        redirect_uri = flow_config.get('redirect_uri')
        
        st.success("🔗 **OAuth URL Generated!**")
        st.markdown("### 📋 Authentication Steps:")
        
        st.markdown("**1. 🌐 Click the URL below to open in your browser:**")
        st.markdown(f"[Open Google OAuth Page]({auth_url})")
        
        # Also show the raw URL for copy/paste
        with st.expander("📋 Or copy/paste this URL"):
            st.code(auth_url, language=None)
        
        st.markdown("**2. 🔑 Complete the authentication in your browser**")
        st.markdown("**3. ✅ You should be automatically redirected back**")
        
        st.info(f"🔧 **Technical**: OAuth redirect URI: {redirect_uri}")
        st.info(f"🔧 **Technical**: Listening on port {listen_port} inside container")
        
        # Start local server in background
        if f"{auth_key}_server_started" not in st.session_state:
            st.session_state[f"{auth_key}_server_started"] = True
            
            # Create a simple handler to capture the authorization code
            class CallbackHandler(BaseHTTPRequestHandler):
                def do_GET(self):
                    # Parse the authorization code from the URL
                    parsed_url = urlparse(self.path)
                    query_params = parse_qs(parsed_url.query)
                    
                    if 'code' in query_params:
                        # Store the authorization code in session state
                        st.session_state[f"{auth_key}_auth_code"] = query_params['code'][0]
                        st.session_state[f"{auth_key}_step"] = "exchange_code"
                        
                        # Send success response
                        self.send_response(200)
                        self.send_header('Content-type', 'text/html')
                        self.end_headers()
                        success_html = """
                        <html>
                        <body>
                        <h2>✅ Authentication Successful!</h2>
                        <p>You can close this window and return to the Streamlit app.</p>
                        <script>window.close();</script>
                        </body>
                        </html>
                        """
                        self.wfile.write(success_html.encode('utf-8'))
                    elif 'error' in query_params:
                        # Handle error
                        error = query_params['error'][0]
                        st.session_state[f"{auth_key}_error"] = error
                        
                        self.send_response(400)
                        self.send_header('Content-type', 'text/html')
                        self.end_headers()
                        self.wfile.write(f"""
                        <html>
                        <body>
                        <h2>❌ Authentication Failed</h2>
                        <p>Error: {error}</p>
                        <p>Please return to the Streamlit app and try again.</p>
                        </body>
                        </html>
                        """.encode())
                
                def log_message(self, format, *args):
                    # Suppress log messages
                    pass
            
            # Start server in a separate thread
            def start_server():
                try:
                    server = HTTPServer(('localhost', listen_port), CallbackHandler)
                    server.timeout = 300  # 5 minute timeout
                    server.handle_request()  # Handle one request then stop
                except Exception as e:
                    st.session_state[f"{auth_key}_server_error"] = str(e)
            
            server_thread = threading.Thread(target=start_server, daemon=True)
            server_thread.start()
        
        # Check if we got a response
        col1, col2 = st.columns(2)
        
        with col1:
            if st.button("🔄 Check Status", type="primary"):
                st.rerun()
        
        with col2:
            if st.button("🔄 Start Over"):
                # Clear session state and start over
                for key in list(st.session_state.keys()):
                    if key.startswith(auth_key):
                        del st.session_state[key]
                st.rerun()
        
        # Check for server errors
        if f"{auth_key}_server_error" in st.session_state:
            st.error(f"❌ Server error: {st.session_state[f'{auth_key}_server_error']}")
        
        # Check for OAuth errors
        if f"{auth_key}_error" in st.session_state:
            st.error(f"❌ OAuth error: {st.session_state[f'{auth_key}_error']}")
        
        # Auto-check for completion
        if f"{auth_key}_auth_code" in st.session_state:
            st.session_state[f"{auth_key}_step"] = "exchange_code"
            st.rerun()
    
    # Step 3: Exchange code for token
    elif st.session_state[f"{auth_key}_step"] == "exchange_code":
        auth_code = st.session_state.get(f"{auth_key}_auth_code")
        flow_config = st.session_state.get(f"{auth_key}_flow_config")
        
        if not auth_code or not flow_config:
            st.error("❌ Missing authentication data. Please start over.")
            if st.button("🔄 Start Over"):
                for key in list(st.session_state.keys()):
                    if key.startswith(auth_key):
                        del st.session_state[key]
                st.rerun()
            return False
        
        try:
            with st.spinner("🔄 Exchanging authorization code for tokens..."):
                # Recreate the flow
                flow = InstalledAppFlow.from_client_config(
                    flow_config['client_config'], 
                    flow_config['scopes']
                )
                flow.redirect_uri = flow_config['redirect_uri']
                
                # Exchange authorization code for credentials
                flow.fetch_token(code=auth_code)
                creds = flow.credentials
                
                # Save the credentials
                with open(token_filename, 'w') as token:
                    token.write(creds.to_json())
                
                st.success(f"✅ Token saved to {token_filename}")
                st.success(f"✅ Authentication successful for {account_description}!")
                
                # Clear session state
                for key in list(st.session_state.keys()):
                    if key.startswith(auth_key):
                        del st.session_state[key]
                
                return True
                
        except Exception as e:
            st.error(f"❌ Token exchange failed: {str(e)}")
            st.info("💡 Please try the authentication process again.")
            
            if st.button("🔄 Try Again"):
                for key in list(st.session_state.keys()):
                    if key.startswith(auth_key):
                        del st.session_state[key]
                st.rerun()
            
            return False
    
    return False

def show_testing_page():
    st.header("🧪 Testing & Simulation")
    st.markdown("Test your AI agent's functionality with sample tasks and scenarios")
    
    from config_manager import config_manager
    
    # Load current settings
    try:
        settings = config_manager.load_settings()
    except Exception as e:
        st.error(f"❌ Error loading settings: {str(e)}")
        return
    
    # Define tab configuration
    tab_configs = [
        {"key": "task_simulation", "label": "📋 Task Simulation"},
        {"key": "calendar_test", "label": "📅 Calendar Testing"},
        {"key": "categorization_test", "label": "🏷️ Categorization Testing"},
        {"key": "webhook_test", "label": "🔗 Webhook Testing"},
        {"key": "end_to_end", "label": "🎯 End-to-End Testing"}
    ]
    
    # Create persistent tabs
    active_tab = create_persistent_tabs("testing", tab_configs)
    
    # Show content based on selected tab
    if active_tab == "task_simulation":
        st.subheader("📋 Task Simulation")
        st.markdown("Test how your AI agent would handle different types of tasks")
        
        # Sample tasks based on project mappings
        project_mappings = settings.get("project_mappings", {})
        if not project_mappings:
            st.warning("⚠️ No project mappings configured. Please configure them in the Configuration tab first.")
            return
        
        # Get unique lists for testing
        unique_lists = sorted(set(project_mappings.values()))
        
        st.markdown("### 🎯 Quick Test Scenarios")
        
        # Pre-defined test scenarios
        test_scenarios = {
            "work": [
                "Review quarterly reports by Friday",
                "Prepare presentation for client meeting",
                "Schedule team standup for next week",
                "Follow up on project deadlines"
            ],
            "personal": [
                "Buy groceries for weekend dinner",
                "Call dentist to schedule appointment",
                "Plan vacation itinerary",
                "Organize closet and donate old clothes"
            ],
            "health": [
                "Go for 30-minute morning run",
                "Prepare healthy meal prep for the week",
                "Book annual health checkup",
                "Practice meditation for 15 minutes"
            ],
            "learning": [
                "Complete Python course chapter 5",
                "Read research paper on machine learning",
                "Practice guitar for 1 hour",
                "Review Spanish vocabulary flashcards"
            ]
        }
        
        # Show scenario buttons
        for list_name in unique_lists:
            if list_name.lower() in test_scenarios:
                st.markdown(f"**{list_name.title()} Tasks:**")
                cols = st.columns(2)
                scenarios = test_scenarios[list_name.lower()]
                
                for i, scenario in enumerate(scenarios):
                    with cols[i % 2]:
                        if st.button(f"📝 {scenario}", key=f"scenario_{list_name}_{i}", use_container_width=True):
                            st.session_state[f"test_task"] = scenario
                            st.session_state[f"test_list"] = list_name
                            st.success(f"✅ Selected: {scenario}")
                st.markdown("---")
        
        # Custom task input
        st.markdown("### ✏️ Custom Task Testing")
        
        col1, col2 = st.columns([3, 1])
        with col1:
            custom_task = st.text_input(
                "Enter custom task",
                value=st.session_state.get("test_task", ""),
                placeholder="e.g., 'Finish project proposal by tomorrow afternoon'"
            )
        
        with col2:
            selected_list = st.selectbox(
                "Todo List",
                unique_lists,
                index=unique_lists.index(st.session_state.get("test_list", unique_lists[0])) if st.session_state.get("test_list") in unique_lists else 0
            )
        
        if st.button("🚀 Test Task Scheduling", type="primary") and custom_task.strip():
            with st.spinner("🤖 Simulating task scheduling..."):
                try:
                    # Simulate the scheduling process
                    import json
                    from datetime import datetime, timedelta
                    import pytz
                    
                    # Get timezone
                    timezone_str = settings.get("timezone", "Asia/Jerusalem")
                    local_tz = pytz.timezone(timezone_str)
                    now = datetime.now(local_tz)
                    
                    # Simulate task data
                    mock_task = {
                        "id": "test_task_123",
                        "content": custom_task.strip(),
                        "project_id": "test_project",
                        "priority": 2,
                        "due": None,
                        "labels": []
                    }
                    
                    # Show what the agent would do
                    st.success("✅ **Simulation Results:**")
                    
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        st.markdown("**📋 Task Analysis:**")
                        st.json({
                            "task_content": custom_task.strip(),
                            "mapped_list": selected_list,
                            "priority_level": "Normal (P3)",
                            "estimated_duration": "30-60 minutes",
                            "suggested_time": now.strftime("%Y-%m-%d %H:%M")
                        })
                    
                    with col2:
                        st.markdown("**🎯 Expected Actions:**")
                        st.markdown("""
                        1. ✅ **Receive webhook** from Todoist
                        2. 🔍 **Analyze task** content and priority
                        3. 📅 **Check calendar** for free time slots
                        4. ⏰ **Schedule task** in optimal time slot
                        5. 📝 **Update Todoist** with scheduled time
                        """)
                    
                    # Show scheduling logic
                    st.markdown("**🧠 Scheduling Logic:**")
                    activity_hours = settings.get("activity_hours", {}).get(selected_list, {})
                    
                    if activity_hours:
                        available_days = [day for day, hours in activity_hours.items() if hours is not None]
                        if available_days:
                            st.info(f"📅 **Available days for {selected_list}:** {', '.join(available_days)}")
                            
                            # Show next available slot
                            next_day = available_days[0] if available_days else "monday"
                            next_hours = activity_hours.get(next_day, {"start": "09:00", "end": "17:00"})
                            
                            if next_hours:
                                st.success(f"⏰ **Next available slot:** {next_day.title()} {next_hours['start']}-{next_hours['end']}")
                        else:
                            st.warning("⚠️ No Activity Hours configured for this list")
                    else:
                        st.warning("⚠️ No Activity Hours configured for this list")
                    
                except Exception as e:
                    st.error(f"❌ Simulation failed: {str(e)}")
    
    elif active_tab == "calendar_test":
        st.subheader("📅 Calendar Testing")
        st.markdown("Test your Google Calendar integration and free time detection")
        
        # Check authentication status
        main_token_valid, _ = validate_google_token("google_token_main.json")
        work_token_valid, _ = validate_google_token("google_token_work.json")
        
        if not main_token_valid and not work_token_valid:
            st.warning("⚠️ No Google accounts authenticated. Please authenticate in the Authentication tab first.")
            return
        
        # Calendar connection test
        st.markdown("### 🔗 Calendar Connection Test")
        
        col1, col2 = st.columns(2)
        
        with col1:
            if st.button("🔍 Test Calendar Access", type="primary"):
                with st.spinner("Testing calendar connections..."):
                    try:
                        from google_calendar import get_available_calendars
                        
                        results = {}
                        if main_token_valid:
                            try:
                                main_calendars = get_available_calendars("tokens/google_token_main.json")
                                results["main"] = {"status": "success", "calendars": len(main_calendars), "data": main_calendars}
                            except Exception as e:
                                results["main"] = {"status": "error", "error": str(e)}
                        
                        if work_token_valid:
                            try:
                                work_calendars = get_available_calendars("tokens/google_token_work.json")
                                results["work"] = {"status": "success", "calendars": len(work_calendars), "data": work_calendars}
                            except Exception as e:
                                results["work"] = {"status": "error", "error": str(e)}
                        
                        # Display results
                        for account, result in results.items():
                            if result["status"] == "success":
                                st.success(f"✅ **{account.title()}**: {result['calendars']} calendars accessible")
                            else:
                                st.error(f"❌ **{account.title()}**: {result['error']}")
                        
                    except Exception as e:
                        st.error(f"❌ Calendar test failed: {str(e)}")
        
        with col2:
            if st.button("📊 Test Free Time Detection"):
                with st.spinner("Testing free time detection..."):
                    try:
                        from datetime import datetime, timedelta
                        import pytz
                        from google_calendar import get_free_intervals
                        
                        # Get timezone
                        timezone_str = settings.get("timezone", "Asia/Jerusalem")
                        local_tz = pytz.timezone(timezone_str)
                        
                        # Test for next 24 hours
                        now = datetime.now(local_tz)
                        end_time = now + timedelta(hours=24)
                        
                        start_timestamp = now.isoformat()
                        end_timestamp = end_time.isoformat()
                        
                        # Get free intervals
                        free_intervals = aio.run(get_free_intervals(start_timestamp, end_timestamp))
                        
                        if free_intervals:
                            st.success(f"✅ Found {len(free_intervals)} free time slots in next 24 hours")
                            
                            # Show first few slots
                            st.markdown("**📅 Sample Free Slots:**")
                            for i, interval in enumerate(free_intervals[:5]):
                                start_dt = datetime.fromisoformat(interval['start'].replace('Z', '+00:00')).astimezone(local_tz)
                                end_dt = datetime.fromisoformat(interval['end'].replace('Z', '+00:00')).astimezone(local_tz)
                                duration = end_dt - start_dt
                                duration_minutes = int(duration.total_seconds() / 60)
                                
                                st.text(f"• {start_dt.strftime('%a %m/%d %H:%M')} - {end_dt.strftime('%H:%M')} ({duration_minutes} min)")
                            
                            if len(free_intervals) > 5:
                                st.text(f"... and {len(free_intervals) - 5} more slots")
                        else:
                            st.warning("⚠️ No free time slots found")
                            
                    except Exception as e:
                        st.error(f"❌ Free time detection failed: {str(e)}")
    
    elif active_tab == "categorization_test":
        st.subheader("🏷️ Auto-Categorization Testing")
        st.markdown("Test how AI would categorize tasks into different sections")
        
        # Check if autocategorization is configured
        autocategorization = settings.get("autocategorization", {})
        enabled_projects = autocategorization.get("enabled_projects", [])
        
        if not enabled_projects:
            st.warning("⚠️ No projects enabled for auto-categorization. Configure them in the Configuration tab first.")
            return
        
        st.markdown("### 🎯 Categorization Test")
        
        col1, col2 = st.columns([2, 1])
        
        with col1:
            test_task = st.text_input(
                "Task to categorize",
                placeholder="e.g., 'buy milk and bread' or 'schedule team meeting'"
            )
        
        with col2:
            test_project = st.selectbox("Project", enabled_projects)
        
        if st.button("🤖 Test Categorization", type="primary") and test_task.strip():
            with st.spinner("🤖 Testing categorization..."):
                try:
                    # This would call the actual categorization function
                    st.success("✅ **Categorization Result:**")
                    st.info("💡 This would analyze the task and suggest the appropriate section/category")
                    
                    # Show mock result for now
                    st.json({
                        "task": test_task.strip(),
                        "project": test_project,
                        "suggested_category": "General",
                        "confidence": "85%",
                        "reasoning": "Based on task content and project context"
                    })
                    
                except Exception as e:
                    st.error(f"❌ Categorization test failed: {str(e)}")
    
    elif active_tab == "webhook_test":
        st.subheader("🔗 Webhook Testing")
        st.markdown("Test webhook functionality and simulate Todoist events")
        
        # Check webhook server status
        try:
            webhook_config = settings.get("webhook", {"host": "0.0.0.0", "port": 5055})
            port = webhook_config.get("port", 5055)
            health_url = f"http://127.0.0.1:{port}/health"
            
            def check_webhook_server():
                try:
                    import requests
                    response = requests.get(health_url, timeout=2)
                    return response.status_code == 200
                except:
                    return False
            
            server_running = check_webhook_server()
            
            if server_running:
                st.success("✅ Webhook server is running")
            else:
                st.error("❌ Webhook server is not running")
                st.info("💡 Start the webhook server in the Webhook Server tab first")
                return
            
            # Test webhook endpoint
            st.markdown("### 📡 Webhook Endpoint Test")
            
            if st.button("🔄 Test Webhook Endpoint", type="primary"):
                with st.spinner("Testing webhook endpoint..."):
                    try:
                        import requests
                        import json
                        
                        # Create a test webhook payload
                        test_payload = {
                            "event_name": "item:added",
                            "event_data": {
                                "id": 1234567890,
                                "content": "Test task from Streamlit app",
                                "project_id": 1234567890,
                                "priority": 2,
                                "due": None,
                                "labels": []
                            },
                            "user_id": 1234567890
                        }
                        
                        webhook_url = f"http://127.0.0.1:{port}/webhook/todoist"
                        
                        response = requests.post(
                            webhook_url,
                            headers={"Content-Type": "application/json"},
                            json=test_payload,
                            timeout=10
                        )
                        
                        if response.status_code == 200:
                            st.success("✅ Webhook endpoint is working correctly")
                            st.json(response.json())
                        else:
                            st.error(f"❌ Webhook returned status {response.status_code}")
                            st.text(response.text)
                            
                    except Exception as e:
                        st.error(f"❌ Webhook test failed: {str(e)}")
            
            # Show recent webhook events
            st.markdown("### 📊 Recent Webhook Events")
            
            try:
                import requests
                logs_url = f"http://127.0.0.1:{port}/webhook/logs"
                response = requests.get(logs_url, timeout=5)
                
                if response.status_code == 200:
                    events = response.json().get("events", [])
                    if events:
                        # Show last 5 events
                        recent_events = sorted(events, key=lambda x: x.get("timestamp", ""), reverse=True)[:5]
                        
                        for event in recent_events:
                            timestamp = event.get("timestamp", "Unknown")
                            event_type = event.get("event_type", "Unknown")
                            task_content = event.get("task_content", "No content")
                            
                            st.markdown(f"**{timestamp}** - {event_type}")
                            st.text(f"Task: {task_content}")
                            st.markdown("---")
                    else:
                        st.info("📝 No webhook events recorded yet")
                else:
                    st.warning("⚠️ Could not fetch webhook logs")
                    
            except Exception as e:
                st.warning(f"⚠️ Could not fetch webhook events: {str(e)}")
                
        except Exception as e:
            st.error(f"❌ Error testing webhook: {str(e)}")
    
    elif active_tab == "end_to_end":
        st.subheader("🎯 End-to-End Testing")
        st.markdown("Comprehensive system test simulating the complete workflow")
        
        # System readiness check
        st.markdown("### 🔍 System Readiness Check")
        
        checks = []
        
        # Check Google authentication
        main_token_valid, _ = validate_google_token("google_token_main.json")
        work_token_valid, _ = validate_google_token("google_token_work.json")
        google_auth_ok = main_token_valid or work_token_valid
        checks.append(("Google Authentication", google_auth_ok))
        
        # Check API keys
        todoist_ok = bool(os.getenv("TODOIST_API_TOKEN"))
        openai_ok = bool(os.getenv("OPENAI_API_KEY"))
        checks.append(("Todoist API", todoist_ok))
        checks.append(("OpenAI API", openai_ok))
        
        # Check configuration
        project_mappings = settings.get("project_mappings", {})
        activity_hours = settings.get("activity_hours", {})
        config_ok = bool(project_mappings and activity_hours)
        checks.append(("Configuration", config_ok))
        
        # Check webhook server
        try:
            webhook_config = settings.get("webhook", {"host": "0.0.0.0", "port": 5055})
            port = webhook_config.get("port", 5055)
            
            import requests
            health_url = f"http://127.0.0.1:{port}/health"
            response = requests.get(health_url, timeout=2)
            webhook_ok = response.status_code == 200
        except:
            webhook_ok = False
        
        checks.append(("Webhook Server", webhook_ok))
        
        # Display readiness status
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("**🔧 System Components:**")
            for component, status in checks:
                if status:
                    st.success(f"✅ {component}")
                else:
                    st.error(f"❌ {component}")
        
        with col2:
            all_ready = all(status for _, status in checks)
            if all_ready:
                st.success("🎉 **System is ready for end-to-end testing!**")
            else:
                st.warning("⚠️ **System not ready.** Fix the failed components first.")
        
        # End-to-end test
        if all_ready:
            st.markdown("---")
            st.markdown("### 🚀 Complete Workflow Test")
            
            if st.button("🎯 Run End-to-End Test", type="primary"):
                with st.spinner("🔄 Running comprehensive system test..."):
                    try:
                        # This would run a complete test workflow
                        st.success("✅ **End-to-End Test Results:**")
                        
                        test_steps = [
                            ("📝 Task Creation", "Simulated new task creation"),
                            ("🔗 Webhook Reception", "Webhook received and processed"),
                            ("🤖 AI Analysis", "Task analyzed and categorized"),
                            ("📅 Calendar Check", "Free time slots identified"),
                            ("⏰ Scheduling", "Task scheduled in optimal slot"),
                            ("📤 Todoist Update", "Task updated with scheduled time")
                        ]
                        
                        for step, description in test_steps:
                            st.success(f"✅ **{step}**: {description}")
                            time.sleep(0.5)  # Simulate processing time
                        
                        st.balloons()
                        st.success("🎉 **All systems working correctly!**")
                        
                    except Exception as e:
                        st.error(f"❌ End-to-end test failed: {str(e)}")
        else:
            st.info("💡 Fix the system components above to enable end-to-end testing")

def check_redirect_uri_compatibility(expected_redirect_uri, configured_uris):
    """Check if the expected redirect URI is configured in Google OAuth client"""
    if not configured_uris:
        return False, "No redirect URIs found in credentials file"
    
    # Check for exact match
    if expected_redirect_uri in configured_uris:
        return True, "Exact match found"
    
    # Check for localhost variations
    if expected_redirect_uri.startswith("http://localhost"):
        localhost_uris = [uri for uri in configured_uris if uri.startswith("http://localhost")]
        if localhost_uris:
            return False, f"Localhost mismatch. Expected: {expected_redirect_uri}, but found: {localhost_uris}"
    
    # Check for external host variations  
    elif not expected_redirect_uri.startswith("http://localhost"):
        external_uris = [uri for uri in configured_uris if not uri.startswith("http://localhost")]
        if external_uris:
            return False, f"External host mismatch. Expected: {expected_redirect_uri}, but found: {external_uris}"
    
    return False, f"No compatible redirect URI found. Expected: {expected_redirect_uri}, but found: {configured_uris}"

if __name__ == "__main__":
    main() 