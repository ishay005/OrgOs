"""State canonicalization - normalize state for consistent comparison.

New JSON structure:
{
  "users": {...},
  "tasks": [
    {"id": "T1", "title": "...", "parent": "T2", "depends_on": ["T3"], ...}
  ]
}
"""

import copy
from typing import Any, Dict, List, Optional, Tuple


def canonicalize_state(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Return a canonical form of the state for comparison.
    
    - Sorts tasks by ID
    - Sorts depends_on arrays
    - Removes None values from tasks
    - Ensures consistent key ordering
    
    Args:
        state: The state to canonicalize
        
    Returns:
        Canonicalized copy of the state
    """
    result = {}
    
    # Users - sorted by id
    users = state.get("users", {})
    result["users"] = {
        uid: {"name": u.get("name", "")}
        for uid in sorted(users.keys())
        for u in [users[uid]]
    }
    
    # Tasks - sorted by id, cleaned
    tasks = state.get("tasks", [])
    sorted_tasks = sorted(tasks, key=lambda t: t.get("id", ""))
    
    result["tasks"] = []
    for task in sorted_tasks:
        clean_task = {}
        for key in sorted(task.keys()):
            val = task[key]
            if val is not None:
                if key == "depends_on" and isinstance(val, list):
                    # Sort depends_on for consistent comparison
                    clean_task[key] = sorted(val)
                else:
                    clean_task[key] = val
        result["tasks"].append(clean_task)
    
    return result


def deep_copy_state(state: Dict[str, Any]) -> Dict[str, Any]:
    """Create a deep copy of a state."""
    return copy.deepcopy(state)


def get_task_by_title(state: Dict[str, Any], title: str) -> Tuple[Optional[str], Optional[Dict]]:
    """
    Find a task by title.
    
    Returns:
        (task_id, task_dict) or (None, None) if not found
    """
    for task in state.get("tasks", []):
        if task.get("title") == title:
            return task.get("id"), task
    return None, None


def get_task_by_id(state: Dict[str, Any], task_id: str) -> Optional[Dict]:
    """Find a task by ID."""
    for task in state.get("tasks", []):
        if task.get("id") == task_id:
            return task
    return None


def get_title_to_id_map(state: Dict[str, Any]) -> Dict[str, str]:
    """Build a title -> task_id mapping."""
    return {
        task.get("title"): task.get("id")
        for task in state.get("tasks", [])
        if task.get("title") and task.get("id")
    }


def get_id_to_title_map(state: Dict[str, Any]) -> Dict[str, str]:
    """Build a task_id -> title mapping."""
    return {
        task.get("id"): task.get("title")
        for task in state.get("tasks", [])
        if task.get("id") and task.get("title")
    }


def build_task_index(state: Dict[str, Any]) -> Dict[str, int]:
    """Build a task_id -> array index mapping."""
    return {
        task.get("id"): i
        for i, task in enumerate(state.get("tasks", []))
        if task.get("id")
    }
