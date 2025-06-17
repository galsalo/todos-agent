# AI Agent System for Auto Task Scheduling

*An autonomous system that automatically schedules Todoist tasks by analyzing calendar availability and making intelligent placement decisions through coordinated AI agents.*

A multi-agent system demonstrating intelligent task scheduling through LLM-powered agents, webhook processing, and calendar integration.

## AI Agent Architecture

This project implements a sophisticated agent system that combines multiple AI components to automate task scheduling decisions:

### **Master Agent** 
- Central orchestrator using LLM-based reasoning
- Processes incoming webhook events with contextual understanding
- Makes intelligent scheduling decisions based on task attributes and calendar availability
- Implements agent communication patterns and state management

### **Auto-Categorization Agent**
- Specialized NLP agent for task classification
- Uses prompt engineering and few-shot learning techniques
- Categorizes tasks based on content, project context, and learned patterns
- Implements category-specific scheduling logic

### **Calendar Analysis Agent**
- Processes calendar data to identify optimal scheduling windows
- Implements time-slot optimization algorithms
- Handles multi-calendar integration (personal/work accounts)
- Manages timezone conversions and conflict detection

## Technical Implementation

### **Agent Communication & Orchestration**
- Event-driven architecture using webhook triggers
- Asynchronous processing with proper error handling and retries
- Agent state persistence and recovery mechanisms
- Centralized logging and monitoring for agent behavior analysis

### **LLM Integration**
- OpenAI API integration with structured prompts
- Context management for multi-turn agent conversations
- Function calling implementation for tool use
- Response parsing and validation

### **Real-time Processing Pipeline**
1. **Webhook ingestion** - Real-time task creation events from Todoist
2. **Agent activation** - Triggers appropriate agent based on event type
3. **Context gathering** - Agents collect relevant data (calendar, task history, preferences)
4. **Decision making** - LLM-powered reasoning for optimal scheduling
5. **Action execution** - API calls to update Todoist and calendar systems

## Key AI Components

### **Intelligent Task Processing**
- Natural language understanding for task content analysis
- Priority and urgency inference from task attributes
- Duration estimation using historical patterns and task complexity
- Dependency detection and scheduling constraint handling

### **Learning & Adaptation**
- User preference learning from scheduling patterns
- Feedback loop integration for continuous improvement
- Activity hour optimization based on user behavior
- Dynamic categorization model updates

### **Multi-Agent Coordination**
- Agent handoff protocols for complex scheduling scenarios
- Conflict resolution between competing scheduling requests
- Resource allocation and queue management
- Distributed decision making with consensus mechanisms

## System Components

- **Agent Lock Manager**: Prevents concurrent agent execution conflicts
- **Central Logger**: Comprehensive logging for agent behavior analysis
- **Config Manager**: Dynamic configuration management for agent parameters
- **Task Processor**: Core agent execution engine with retry logic
- **Webhook Server**: Real-time event processing and agent triggering
- **Streamlit Dashboard**: Agent monitoring and configuration interface

## Technical Skills Demonstrated

- **AI Agent Development**: Multi-agent system design and implementation
- **LLM Engineering**: Prompt design, function calling, and response handling
- **Real-time Processing**: Webhook handling and event-driven architecture
- **API Integration**: Complex multi-service orchestration (Todoist, Google Calendar, OpenAI)
- **Async Programming**: Concurrent processing with proper error handling
- **System Design**: Scalable architecture with monitoring and logging 
