"""State legality validation - checks all constraints on a state.

New JSON structure:
{
  "users": {...},
  "tasks": [
    {"id": "T1", "title": "...", "parent": "T2", "depends_on": ["T3"], ...}
  ]
}
"""

from typing import Any, Dict, List, Set


# Valid enum values
VALID_PRIORITIES = {"Critical", "High", "Medium", "Low"}
VALID_STATUSES = {"Not started", "In progress", "Blocked", "Done"}
VALID_STATES = {"DRAFT", "ACTIVE", "REJECTED", "ARCHIVED"}


def validate_state(state: Dict[str, Any]) -> List[Dict[str, str]]:
    """
    Validate a state for legality.
    
    Args:
        state: The state to validate
        
    Returns:
        List of error dicts with 'path' and 'message' keys.
        Empty list means state is valid.
    """
    errors: List[Dict[str, str]] = []
    
    # Basic structure checks
    if not isinstance(state, dict):
        errors.append({"path": "", "message": "State must be a dict"})
        return errors
    
    # Validate users
    users = state.get("users", {})
    if not isinstance(users, dict):
        errors.append({"path": "users", "message": "users must be a dict"})
    else:
        for user_id, user in users.items():
            if not isinstance(user, dict):
                errors.append({
                    "path": f"users.{user_id}",
                    "message": "user must be a dict"
                })
            elif "name" not in user:
                errors.append({
                    "path": f"users.{user_id}",
                    "message": "user missing 'name'"
                })
            elif not isinstance(user["name"], str):
                errors.append({
                    "path": f"users.{user_id}.name",
                    "message": "name must be a string"
                })
    
    # Validate tasks (now an array)
    tasks_list = state.get("tasks", [])
    if not isinstance(tasks_list, list):
        errors.append({"path": "tasks", "message": "tasks must be an array"})
        tasks_list = []
    
    # Build task index for reference validation
    task_ids: Set[str] = set()
    titles: Dict[str, str] = {}  # title -> task_id
    
    for i, task in enumerate(tasks_list):
        path = f"tasks[{i}]"
        
        if not isinstance(task, dict):
            errors.append({"path": path, "message": "task must be a dict"})
            continue
        
        # Required: id
        task_id = task.get("id")
        if task_id is None:
            errors.append({"path": f"{path}.id", "message": "id is required"})
            continue
        elif not isinstance(task_id, str):
            errors.append({"path": f"{path}.id", "message": "id must be a string"})
            continue
        elif task_id in task_ids:
            errors.append({
                "path": f"{path}.id",
                "message": f"duplicate task id: {task_id}"
            })
        else:
            task_ids.add(task_id)
        
        # Required: title
        title = task.get("title")
        if title is None:
            errors.append({"path": f"{path}.title", "message": "title is required"})
        elif not isinstance(title, str):
            errors.append({"path": f"{path}.title", "message": "title must be a string"})
        else:
            if title in titles:
                errors.append({
                    "path": f"{path}.title",
                    "message": f"duplicate title '{title}' (also in {titles[title]})"
                })
            else:
                titles[title] = task_id
        
        # Optional enum: priority
        if "priority" in task and task["priority"] is not None:
            if task["priority"] not in VALID_PRIORITIES:
                errors.append({
                    "path": f"{path}.priority",
                    "message": f"invalid priority: {task['priority']}"
                })
        
        # Optional enum: status
        if "status" in task and task["status"] is not None:
            if task["status"] not in VALID_STATUSES:
                errors.append({
                    "path": f"{path}.status",
                    "message": f"invalid status: {task['status']}"
                })
        
        # Optional enum: state
        if "state" in task and task["state"] is not None:
            if task["state"] not in VALID_STATES:
                errors.append({
                    "path": f"{path}.state",
                    "message": f"invalid state: {task['state']}"
                })
        
        # Optional int: impact_size
        if "impact_size" in task and task["impact_size"] is not None:
            impact = task["impact_size"]
            if not isinstance(impact, int) or impact < 1 or impact > 5:
                errors.append({
                    "path": f"{path}.impact_size",
                    "message": f"impact_size must be int 1-5: {impact}"
                })
        
        # Optional ref: owner
        if "owner" in task and task["owner"] is not None:
            if task["owner"] not in users:
                errors.append({
                    "path": f"{path}.owner",
                    "message": f"owner not in users: {task['owner']}"
                })
        
        # Optional ref: created_by
        if "created_by" in task and task["created_by"] is not None:
            if task["created_by"] not in users:
                errors.append({
                    "path": f"{path}.created_by",
                    "message": f"created_by not in users: {task['created_by']}"
                })
        
        # depends_on must be an array
        if "depends_on" in task:
            deps = task["depends_on"]
            if deps is not None and not isinstance(deps, list):
                errors.append({
                    "path": f"{path}.depends_on",
                    "message": "depends_on must be an array"
                })
    
    # Second pass: validate references (parent and depends_on)
    for i, task in enumerate(tasks_list):
        if not isinstance(task, dict) or "id" not in task:
            continue
        
        task_id = task["id"]
        path = f"tasks[{i}]"
        
        # Optional ref: parent
        if "parent" in task and task["parent"] is not None:
            if task["parent"] not in task_ids:
                errors.append({
                    "path": f"{path}.parent",
                    "message": f"parent not in tasks: {task['parent']}"
                })
        
        # depends_on references
        if "depends_on" in task and isinstance(task["depends_on"], list):
            for j, dep_id in enumerate(task["depends_on"]):
                if dep_id not in task_ids:
                    errors.append({
                        "path": f"{path}.depends_on[{j}]",
                        "message": f"depends_on reference not in tasks: {dep_id}"
                    })
                if dep_id == task_id:
                    errors.append({
                        "path": f"{path}.depends_on[{j}]",
                        "message": "self-dependency not allowed"
                    })
    
    # Build task dict for cycle checks
    tasks_dict = {task["id"]: task for task in tasks_list if isinstance(task, dict) and "id" in task}
    
    # Check parent graph for cycles
    parent_cycle_errors = _check_parent_cycles(tasks_dict)
    errors.extend(parent_cycle_errors)
    
    # Check dependency DAG for cycles
    dep_cycle_errors = _check_dependency_cycles(tasks_dict)
    errors.extend(dep_cycle_errors)
    
    return errors


def _check_parent_cycles(tasks: Dict[str, Any]) -> List[Dict[str, str]]:
    """Check that parent pointers form a forest (no cycles)."""
    errors = []
    
    def find_cycle(task_id: str, visited: Set[str], path: List[str]) -> bool:
        if task_id in visited:
            cycle_start = path.index(task_id)
            cycle = " -> ".join(path[cycle_start:] + [task_id])
            errors.append({
                "path": f"tasks.{task_id}.parent",
                "message": f"parent cycle detected: {cycle}"
            })
            return True
        
        visited.add(task_id)
        path.append(task_id)
        
        task = tasks.get(task_id)
        if task and task.get("parent"):
            parent_id = task["parent"]
            if parent_id in tasks:
                if find_cycle(parent_id, visited, path):
                    return True
        
        path.pop()
        return False
    
    checked: Set[str] = set()
    for task_id in tasks:
        if task_id not in checked:
            visited: Set[str] = set()
            find_cycle(task_id, visited, [])
            checked.update(visited)
    
    return errors


def _check_dependency_cycles(tasks: Dict[str, Any]) -> List[Dict[str, str]]:
    """Check that dependencies form a DAG (no cycles)."""
    errors = []
    
    # Build adjacency list from depends_on
    graph: Dict[str, Set[str]] = {tid: set() for tid in tasks}
    
    for task_id, task in tasks.items():
        for dep_id in task.get("depends_on", []):
            if dep_id in tasks:
                graph[task_id].add(dep_id)
    
    # DFS to find cycles
    WHITE, GRAY, BLACK = 0, 1, 2
    color = {tid: WHITE for tid in tasks}
    
    def dfs(node: str, path: List[str]) -> bool:
        color[node] = GRAY
        path.append(node)
        
        for neighbor in graph[node]:
            if color[neighbor] == GRAY:
                # Found cycle
                cycle_start = path.index(neighbor)
                cycle = " -> ".join(path[cycle_start:] + [neighbor])
                errors.append({
                    "path": "tasks",
                    "message": f"dependency cycle detected: {cycle}"
                })
                return True
            elif color[neighbor] == WHITE:
                if dfs(neighbor, path):
                    return True
        
        path.pop()
        color[node] = BLACK
        return False
    
    for task_id in tasks:
        if color[task_id] == WHITE:
            if dfs(task_id, []):
                break  # Stop after first cycle found
    
    return errors
