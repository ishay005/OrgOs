"""Operations executor - applies ops to transform partial state into produced state.

New JSON structure:
{
  "users": {...},
  "tasks": [
    {"id": "T1", "title": "...", "parent": "T2", "depends_on": ["T3"], ...}
  ]
}
"""

import copy
import re
from typing import Any, Dict, List, Optional, Union


class ExecutorError(Exception):
    """Error during operation execution."""
    pass


def apply_ops(
    state: Dict[str, Any],
    ops: Union[List[Dict], Dict[str, Any]],
    delete_mode: str = "strict"
) -> Dict[str, Any]:
    """
    Apply a list of operations to a state, returning a new state.
    
    Args:
        state: The input state with tasks as array
        ops: Either a list of operations or {"ops": [...]}
        delete_mode: "strict" enforces no children/active deps for delete
        
    Returns:
        New state after applying all operations
    """
    # Deep copy to avoid mutating input
    new_state = copy.deepcopy(state)
    
    # Normalize ops format - handle various model response formats
    if isinstance(ops, dict):
        if "ops" in ops:
            ops_list = ops["ops"]
        elif "operations" in ops:
            ops_list = ops["operations"]
        elif "changes" in ops:
            ops_list = ops["changes"]
        elif len(ops) == 1:
            # Single key dict, use its value if it's a list
            key = list(ops.keys())[0]
            if isinstance(ops[key], list):
                ops_list = ops[key]
            else:
                raise ExecutorError(f"ops object must contain 'ops' key, got: {list(ops.keys())}")
        else:
            raise ExecutorError(f"ops object must contain 'ops' key, got: {list(ops.keys())}")
    elif isinstance(ops, list):
        ops_list = ops
    else:
        raise ExecutorError(f"ops must be list or dict, got {type(ops)}")
    
    # Ensure state has required top-level keys
    if "users" not in new_state:
        new_state["users"] = {}
    if "tasks" not in new_state:
        new_state["tasks"] = []
    
    # Build task index for quick lookup
    task_index = _build_task_index(new_state["tasks"])
    
    # Track temp_id -> real_id mapping
    temp_id_map: Dict[str, str] = {}
    
    # Find next available task ID
    next_id = _get_next_task_id(new_state["tasks"])
    
    # PHASE 1: Pre-scan TASK_CREATE ops to build temp_id_map first
    # This allows forward references between new tasks (e.g., new1 depends on new2)
    for op in ops_list:
        if isinstance(op, dict) and op.get("op") == "TASK_CREATE":
            temp_id = op.get("temp_id")
            if temp_id and temp_id not in temp_id_map:
                temp_id_map[temp_id] = f"T{next_id}"
                next_id += 1
    
    # Reset next_id for actual creation
    next_id = _get_next_task_id(new_state["tasks"])
    
    # PHASE 2: Process each operation
    for i, op in enumerate(ops_list):
        if not isinstance(op, dict):
            raise ExecutorError(f"Operation {i} is not a dict: {op}")
        
        op_type = op.get("op")
        if not op_type:
            raise ExecutorError(f"Operation {i} missing 'op' field: {op}")
        
        try:
            if op_type == "TASK_CREATE":
                next_id = _exec_task_create(new_state, op, temp_id_map, task_index, next_id)
            elif op_type == "TASK_UPDATE":
                _exec_task_update(new_state, op, temp_id_map, task_index)
            elif op_type == "SET_PARENT":
                _exec_set_parent(new_state, op, temp_id_map, task_index)
            elif op_type == "ADD_DEPENDENCY":
                _exec_add_dependency(new_state, op, temp_id_map, task_index)
            elif op_type == "REMOVE_DEPENDENCY":
                _exec_remove_dependency(new_state, op, temp_id_map, task_index)
            elif op_type == "TASK_DELETE":
                _exec_task_delete(new_state, op, temp_id_map, task_index, delete_mode)
            else:
                raise ExecutorError(f"Unknown operation type: {op_type}")
        except ExecutorError:
            raise
        except Exception as e:
            raise ExecutorError(f"Error executing op {i} ({op_type}): {e}")
    
    return new_state


def _build_task_index(tasks: List[Dict]) -> Dict[str, int]:
    """Build a dict mapping task_id -> index in tasks array."""
    return {task["id"]: i for i, task in enumerate(tasks)}


def _get_next_task_id(tasks: List[Dict]) -> int:
    """Find the next available task ID number."""
    max_id = 0
    pattern = re.compile(r"^T(\d+)$")
    for task in tasks:
        match = pattern.match(task.get("id", ""))
        if match:
            max_id = max(max_id, int(match.group(1)))
    return max_id + 1


def _resolve_id(ref: str, temp_id_map: Dict[str, str], task_index: Dict[str, int]) -> str:
    """Resolve a reference which could be a temp_id or real task_id."""
    if ref in temp_id_map:
        return temp_id_map[ref]
    if ref in task_index:
        return ref
    raise ExecutorError(f"Unknown reference: {ref}")


def _get_task(state: Dict, task_id: str, task_index: Dict[str, int]) -> Dict:
    """Get a task by ID."""
    if task_id not in task_index:
        raise ExecutorError(f"Task not found: {task_id}")
    return state["tasks"][task_index[task_id]]


def _exec_task_create(
    state: Dict[str, Any],
    op: Dict[str, Any],
    temp_id_map: Dict[str, str],
    task_index: Dict[str, int],
    next_id: int
) -> int:
    """Execute TASK_CREATE operation.
    
    New format: all fields in single op
      {"op": "TASK_CREATE", "temp_id": "new1", "title": "X", "priority": "High", ...}
    """
    temp_id = op.get("temp_id")
    if not temp_id:
        raise ExecutorError("TASK_CREATE requires 'temp_id'")
    
    # Get pre-assigned ID from temp_id_map (set in phase 1)
    # or create new one if not pre-registered
    if temp_id in temp_id_map:
        new_id = temp_id_map[temp_id]
        # Check if task already created (duplicate TASK_CREATE)
        if new_id in task_index:
            raise ExecutorError(f"Duplicate TASK_CREATE for temp_id: {temp_id}")
    else:
        # Not pre-registered, assign new ID
        new_id = f"T{next_id}"
        temp_id_map[temp_id] = new_id
    
    # Initialize task with id
    task = {"id": new_id, "depends_on": []}
    state["tasks"].append(task)
    task_index[new_id] = len(state["tasks"]) - 1
    
    # Copy all fields from op (except op and temp_id)
    task_fields = ["title", "priority", "status", "state", "impact_size", 
                   "owner", "created_by", "perceived_owner", "main_goal", "resources"]
    
    for field in task_fields:
        value = op.get(field)
        if value is not None:
            if field == "title":
                _check_title_unique(state, new_id, value)
            task[field] = value
    
    # Handle parent reference
    parent = op.get("parent")
    if parent is not None:
        task["parent"] = _resolve_id(parent, temp_id_map, task_index)
    
    # Handle depends_on array
    depends_on = op.get("depends_on")
    if depends_on is not None and isinstance(depends_on, list):
        task["depends_on"] = [_resolve_id(d, temp_id_map, task_index) for d in depends_on]
    
    return next_id + 1


def _check_title_unique(state: Dict, exclude_id: str, title: str) -> None:
    """Check that title is unique among tasks."""
    for task in state["tasks"]:
        if task["id"] != exclude_id and task.get("title") == title:
            raise ExecutorError(f"Duplicate title: {title}")


def _exec_task_update(
    state: Dict[str, Any],
    op: Dict[str, Any],
    temp_id_map: Dict[str, str],
    task_index: Dict[str, int]
) -> None:
    """Execute TASK_UPDATE operation."""
    task_ref = op.get("id") or op.get("task")
    if not task_ref:
        raise ExecutorError("TASK_UPDATE requires 'id'")
    
    task_id = _resolve_id(task_ref, temp_id_map, task_index)
    task = _get_task(state, task_id, task_index)
    
    # New format: single field
    if op.get("field") is not None:
        key = op["field"]
        value = op.get("value")
        _apply_field_update(state, task, key, value, temp_id_map, task_index)
    else:
        # Old format: patch dict
        patch = op.get("patch") or op.get("fields", {})
        if patch and isinstance(patch, dict):
            for key, value in patch.items():
                if value is not None:
                    _apply_field_update(state, task, key, value, temp_id_map, task_index)


def _apply_field_update(
    state: Dict,
    task: Dict,
    key: str,
    value: Any,
    temp_id_map: Dict[str, str],
    task_index: Dict[str, int]
) -> None:
    """Apply a single field update to a task."""
    if value is None:
        return
    
    task_id = task["id"]
    
    if key == "parent":
        if value is None or value == "null":
            task["parent"] = None
        else:
            task["parent"] = _resolve_id(value, temp_id_map, task_index)
    elif key == "title":
        _check_title_unique(state, task_id, value)
        task["title"] = value
    elif key == "depends_on":
        # Allow setting depends_on as array
        if isinstance(value, list):
            task["depends_on"] = [_resolve_id(d, temp_id_map, task_index) for d in value]
        else:
            task["depends_on"] = value
    else:
        task[key] = value


def _exec_set_parent(
    state: Dict[str, Any],
    op: Dict[str, Any],
    temp_id_map: Dict[str, str],
    task_index: Dict[str, int]
) -> None:
    """Execute SET_PARENT operation."""
    child_ref = op.get("child")
    if not child_ref:
        raise ExecutorError("SET_PARENT requires 'child'")
    
    child_id = _resolve_id(child_ref, temp_id_map, task_index)
    task = _get_task(state, child_id, task_index)
    
    parent_ref = op.get("parent")
    if parent_ref is None or parent_ref == "null":
        task["parent"] = None
    else:
        parent_id = _resolve_id(parent_ref, temp_id_map, task_index)
        task["parent"] = parent_id


def _exec_add_dependency(
    state: Dict[str, Any],
    op: Dict[str, Any],
    temp_id_map: Dict[str, str],
    task_index: Dict[str, int]
) -> None:
    """Execute ADD_DEPENDENCY operation - add a dependency to a task."""
    task_ref = op.get("task") or op.get("id")
    depends_on_ref = op.get("depends_on")
    
    if not task_ref:
        raise ExecutorError("ADD_DEPENDENCY requires 'task'")
    if not depends_on_ref:
        raise ExecutorError("ADD_DEPENDENCY requires 'depends_on'")
    
    task_id = _resolve_id(task_ref, temp_id_map, task_index)
    depends_on_id = _resolve_id(depends_on_ref, temp_id_map, task_index)
    
    if task_id == depends_on_id:
        raise ExecutorError("Self-dependency not allowed")
    
    task = _get_task(state, task_id, task_index)
    
    # Ensure depends_on array exists
    if "depends_on" not in task:
        task["depends_on"] = []
    
    # Add if not already present
    if depends_on_id not in task["depends_on"]:
        task["depends_on"].append(depends_on_id)


def _exec_remove_dependency(
    state: Dict[str, Any],
    op: Dict[str, Any],
    temp_id_map: Dict[str, str],
    task_index: Dict[str, int]
) -> None:
    """Execute REMOVE_DEPENDENCY operation - remove a dependency from a task."""
    task_ref = op.get("task") or op.get("id")
    depends_on_ref = op.get("depends_on")
    
    if not task_ref:
        raise ExecutorError("REMOVE_DEPENDENCY requires 'task'")
    if not depends_on_ref:
        raise ExecutorError("REMOVE_DEPENDENCY requires 'depends_on'")
    
    task_id = _resolve_id(task_ref, temp_id_map, task_index)
    depends_on_id = _resolve_id(depends_on_ref, temp_id_map, task_index)
    
    task = _get_task(state, task_id, task_index)
    
    if "depends_on" in task and depends_on_id in task["depends_on"]:
        task["depends_on"].remove(depends_on_id)


def _exec_task_delete(
    state: Dict[str, Any],
    op: Dict[str, Any],
    temp_id_map: Dict[str, str],
    task_index: Dict[str, int],
    delete_mode: str
) -> None:
    """Execute TASK_DELETE operation."""
    task_ref = op.get("id")
    if not task_ref:
        raise ExecutorError("TASK_DELETE requires 'id'")
    
    task_id = _resolve_id(task_ref, temp_id_map, task_index)
    
    if delete_mode == "strict":
        # Check for children
        for task in state["tasks"]:
            if task.get("parent") == task_id:
                raise ExecutorError(f"Cannot delete task {task_id}: has child {task['id']}")
        
        # Check if any task depends on this one
        for task in state["tasks"]:
            if task_id in task.get("depends_on", []):
                raise ExecutorError(f"Cannot delete task {task_id}: task {task['id']} depends on it")
    
    # Remove task from array
    idx = task_index[task_id]
    state["tasks"].pop(idx)
    
    # Remove from all depends_on lists
    for task in state["tasks"]:
        if "depends_on" in task and task_id in task["depends_on"]:
            task["depends_on"].remove(task_id)
    
    # Rebuild index
    task_index.clear()
    task_index.update(_build_task_index(state["tasks"]))
