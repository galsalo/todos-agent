"""
Agent lock system to prevent webhook cascades.

This prevents new webhook processing while an agent is actively working,
which stops agent actions from triggering more agent actions.
"""
import asyncio
import time
from datetime import datetime
from typing import Optional

class AgentLock:
    """Simple global lock to prevent webhook processing during agent work."""
    
    def __init__(self):
        self._lock = asyncio.Lock()
        self._is_agent_working = False
        self._is_cooldown = False
        self._agent_start_time = None
        self._cooldown_start_time = None
        self._current_task_id = None
        self._timeout_seconds = 300  # 5 minute timeout to prevent deadlocks
        self._cooldown_seconds = 3  # 3 second cooldown after agent finishes
    
    async def acquire_agent_lock(self, task_id: str, operation: str = "processing") -> bool:
        """
        Acquire the agent lock for a specific task.
        
        Args:
            task_id: ID of the task being processed
            operation: Description of the operation (for logging)
            
        Returns:
            bool: True if lock acquired, False if already locked
        """
        async with self._lock:
            # Check if we're in cooldown period
            if self._is_cooldown:
                if self._cooldown_start_time and (time.time() - self._cooldown_start_time) > self._cooldown_seconds:
                    # Cooldown expired, fully release
                    print(f"❄️ COOLDOWN EXPIRED: Fully releasing lock after {self._cooldown_seconds}s cooldown")
                    self._is_cooldown = False
                    self._cooldown_start_time = None
                    self._current_task_id = None
                else:
                    # Still in cooldown
                    remaining = self._cooldown_seconds - (time.time() - self._cooldown_start_time)
                    print(f"❄️ AGENT COOLDOWN: Cannot process task {task_id} - cooling down from task {self._current_task_id} ({remaining:.1f}s remaining)")
                    return False
            
            # Check if another agent is already working
            if self._is_agent_working:
                # Check for timeout (safety mechanism)
                if self._agent_start_time and (time.time() - self._agent_start_time) > self._timeout_seconds:
                    print(f"⚠️ AGENT LOCK TIMEOUT: Forcing release after {self._timeout_seconds}s")
                    self._is_agent_working = False
                    self._is_cooldown = False
                    self._current_task_id = None
                else:
                    print(f"🔒 AGENT BUSY: Cannot process task {task_id} - agent working on task {self._current_task_id}")
                    return False
            
            # Acquire the lock
            self._is_agent_working = True
            self._is_cooldown = False  # Clear any existing cooldown
            self._agent_start_time = time.time()
            self._cooldown_start_time = None
            self._current_task_id = task_id
            print(f"🔒 AGENT LOCK ACQUIRED: Starting {operation} for task {task_id}")
            return True
    
    async def release_agent_lock(self, task_id: str):
        """
        Release the agent lock and start cooldown period.
        
        Args:
            task_id: ID of the task that was being processed
        """
        async with self._lock:
            if self._current_task_id == task_id or not self._is_agent_working:
                self._is_agent_working = False
                self._is_cooldown = True
                self._cooldown_start_time = time.time()
                elapsed = time.time() - self._agent_start_time if self._agent_start_time else 0
                print(f"🔓 AGENT WORK COMPLETED: Task {task_id} finished in {elapsed:.1f}s")
                print(f"❄️ COOLDOWN STARTED: Blocking webhooks for {self._cooldown_seconds}s to prevent cascades")
            else:
                print(f"⚠️ AGENT LOCK MISMATCH: Task {task_id} tried to release lock held by {self._current_task_id}")
    
    def is_agent_working(self) -> bool:
        """Check if an agent is currently working or in cooldown."""
        # Check for main timeout
        if self._is_agent_working and self._agent_start_time:
            if (time.time() - self._agent_start_time) > self._timeout_seconds:
                print(f"⚠️ AGENT LOCK EXPIRED: Auto-releasing after timeout")
                self._is_agent_working = False
                self._is_cooldown = False
                self._current_task_id = None
                return False
        
        # Check for cooldown timeout
        if self._is_cooldown and self._cooldown_start_time:
            if (time.time() - self._cooldown_start_time) > self._cooldown_seconds:
                print(f"❄️ COOLDOWN EXPIRED: Fully releasing lock")
                self._is_cooldown = False
                self._cooldown_start_time = None
                self._current_task_id = None
                return False
        
        return self._is_agent_working or self._is_cooldown
    
    def get_status(self) -> dict:
        """Get current lock status."""
        status = {
            "is_locked": self._is_agent_working or self._is_cooldown,
            "is_agent_working": self._is_agent_working,
            "is_cooldown": self._is_cooldown,
            "current_task_id": self._current_task_id,
        }
        
        if self._agent_start_time:
            status["agent_start_time"] = datetime.fromtimestamp(self._agent_start_time).isoformat()
            status["agent_elapsed_seconds"] = time.time() - self._agent_start_time
        
        if self._cooldown_start_time:
            status["cooldown_start_time"] = datetime.fromtimestamp(self._cooldown_start_time).isoformat()
            status["cooldown_elapsed_seconds"] = time.time() - self._cooldown_start_time
            status["cooldown_remaining_seconds"] = max(0, self._cooldown_seconds - (time.time() - self._cooldown_start_time))
        
        return status

# Global agent lock instance
agent_lock = AgentLock()

# Context manager for easy use
class agent_working:
    """Context manager for agent operations."""
    
    def __init__(self, task_id: str, operation: str = "processing"):
        self.task_id = task_id
        self.operation = operation
        self.acquired = False
    
    async def __aenter__(self):
        self.acquired = await agent_lock.acquire_agent_lock(self.task_id, self.operation)
        if not self.acquired:
            raise Exception(f"Agent is busy, cannot process task {self.task_id}")
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.acquired:
            await agent_lock.release_agent_lock(self.task_id) 