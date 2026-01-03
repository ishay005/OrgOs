"""Case generation - creates partial states and prompts from targets.

New JSON structure:
{
  "users": {...},
  "tasks": [
    {"id": "T1", "title": "...", "parent": "T2", "depends_on": ["T3"], ...}
  ]
}
"""

import copy
import random
from typing import Any, Dict, List, Set

from .prompt_render import PROMPT_FORMATS, render_prompt
from .legality import validate_state
from .canonicalize import get_id_to_title_map


# Bucket distribution - now includes PARENT and DEPENDENCY
BUCKET_WEIGHTS = {
    "ADD": 0.15,
    "EDIT": 0.25,
    "DELETE": 0.15,
    "PARENT": 0.15,
    "DEPENDENCY": 0.15,
    "MIXED": 0.15,
}

BUCKETS = list(BUCKET_WEIGHTS.keys())


def generate_cases_for_target(
    target: Dict[str, Any],
    target_id: int,
    num_cases: int,
    seed: int,
    complex_mode: bool = False,
    ultra_mode: bool = False
) -> List[Dict[str, Any]]:
    """
    Generate test cases for a single target.
    
    Args:
        complex_mode: If True, generate more complex operation combinations
        ultra_mode: If True, generate ultra-complex cases (50%+ mixed/multi-op)
    """
    rng = random.Random(seed)
    cases = []
    
    for case_idx in range(num_cases):
        case_seed = seed + case_idx
        case_rng = random.Random(case_seed)
        
        if ultra_mode:
            bucket = _select_bucket_ultra(case_rng)
        elif complex_mode:
            bucket = _select_bucket_complex(case_rng)
        else:
            bucket = _select_bucket(case_rng)
        prompt_format = case_rng.choice(PROMPT_FORMATS)
        
        try:
            case = _generate_case(
                target=target,
                target_id=target_id,
                case_idx=case_idx,
                bucket=bucket,
                prompt_format=prompt_format,
                rng=case_rng
            )
            cases.append(case)
        except Exception as e:
            case = _generate_simple_edit_case(
                target=target,
                target_id=target_id,
                case_idx=case_idx,
                prompt_format=prompt_format,
                rng=case_rng
            )
            cases.append(case)
    
    return cases


def _select_bucket(rng: random.Random) -> str:
    """Select a bucket based on weights."""
    r = rng.random()
    cumulative = 0.0
    for bucket, weight in BUCKET_WEIGHTS.items():
        cumulative += weight
        if r < cumulative:
            return bucket
    return "EDIT"


# Complex mode bucket weights - more MIXED and multi-op cases
COMPLEX_BUCKET_WEIGHTS = {
    "ADD": 0.10,         # 10% - add tasks with parent/dep
    "EDIT": 0.10,        # 10% - multi-field edits
    "DELETE": 0.10,      # 10% - delete with cascade
    "MIXED": 0.35,       # 35% - add + edit + parent + dep
    "PARENT": 0.10,      # 10% - complex parent changes
    "DEPENDENCY": 0.10,  # 10% - complex dep changes
    "MULTI_OP": 0.15,    # 15% - many operations combined
}

# Ultra mode bucket weights - 50%+ MIXED/MULTI_OP, more operations per case
ULTRA_BUCKET_WEIGHTS = {
    "ADD": 0.05,          # 5% - add many tasks with complex relations
    "EDIT": 0.05,         # 5% - many field edits
    "DELETE": 0.05,       # 5% - complex deletes
    "MIXED": 0.30,        # 30% - complex mix
    "PARENT": 0.05,       # 5% - many parent changes
    "DEPENDENCY": 0.05,   # 5% - many dep changes
    "MULTI_OP": 0.25,     # 25% - very many operations
    "ULTRA_MIXED": 0.20,  # 20% - ultra complex mix (new)
}


def _select_bucket_complex(rng: random.Random) -> str:
    """Select a bucket for complex mode with more mixed operations."""
    r = rng.random()
    cumulative = 0.0
    for bucket, weight in COMPLEX_BUCKET_WEIGHTS.items():
        cumulative += weight
        if r < cumulative:
            return bucket
    return "MIXED"


def _select_bucket_ultra(rng: random.Random) -> str:
    """Select a bucket for ultra mode with 50%+ mixed/multi-op cases."""
    r = rng.random()
    cumulative = 0.0
    for bucket, weight in ULTRA_BUCKET_WEIGHTS.items():
        cumulative += weight
        if r < cumulative:
            return bucket
    return "ULTRA_MIXED"


def _generate_case(
    target: Dict[str, Any],
    target_id: int,
    case_idx: int,
    bucket: str,
    prompt_format: str,
    rng: random.Random
) -> Dict[str, Any]:
    """Generate a single test case."""
    
    if bucket == "ADD":
        return _generate_add_case(target, target_id, case_idx, prompt_format, rng)
    elif bucket == "EDIT":
        return _generate_edit_case(target, target_id, case_idx, prompt_format, rng)
    elif bucket == "DELETE":
        return _generate_delete_case(target, target_id, case_idx, prompt_format, rng)
    elif bucket == "PARENT":
        return _generate_parent_case(target, target_id, case_idx, prompt_format, rng)
    elif bucket == "DEPENDENCY":
        return _generate_dependency_case(target, target_id, case_idx, prompt_format, rng)
    elif bucket == "MULTI_OP":
        return _generate_multi_op_case(target, target_id, case_idx, prompt_format, rng)
    elif bucket == "ULTRA_MIXED":
        return _generate_ultra_mixed_case(target, target_id, case_idx, prompt_format, rng)
    else:  # MIXED
        return _generate_mixed_case(target, target_id, case_idx, prompt_format, rng)


def _get_task_by_id(tasks: List[Dict], task_id: str) -> Dict:
    """Find task by ID."""
    for task in tasks:
        if task.get("id") == task_id:
            return task
    return None


def _get_task_index(tasks: List[Dict], task_id: str) -> int:
    """Get index of task by ID."""
    for i, task in enumerate(tasks):
        if task.get("id") == task_id:
            return i
    return -1


def _generate_add_case(
    target: Dict[str, Any],
    target_id: int,
    case_idx: int,
    prompt_format: str,
    rng: random.Random
) -> Dict[str, Any]:
    """Generate ADD case - remove tasks from partial, prompt to add them back."""
    partial = copy.deepcopy(target)
    tasks = partial["tasks"]
    
    if len(tasks) <= 1:
        return _generate_simple_edit_case(target, target_id, case_idx, prompt_format, rng)
    
    # Build child set
    children = set()
    for task in tasks:
        if task.get("parent"):
            children.add(task["parent"])
    
    # Find leaf tasks (not a parent of anyone)
    leaves = [task["id"] for task in tasks if task["id"] not in children]
    
    if not leaves:
        leaves = [task["id"] for task in tasks]
    
    # Remove 1-3 tasks
    num_to_remove = min(len(leaves), rng.randint(1, 3))
    to_remove = set(rng.sample(leaves, num_to_remove))
    
    # Build id->title map for resolving references in prompts
    id_to_title = {t["id"]: t["title"] for t in target["tasks"]}
    
    # Track tasks being removed (include depends_on converted to titles)
    removed_tasks = []
    for task in tasks:
        if task["id"] in to_remove:
            fields = {k: v for k, v in task.items() if k not in ("title", "id")}
            # Convert depends_on IDs to titles for the prompt
            if "depends_on" in fields and fields["depends_on"]:
                fields["depends_on"] = [id_to_title.get(d, d) for d in fields["depends_on"]]
            # Convert parent ID to title for the prompt
            if "parent" in fields and fields["parent"]:
                fields["parent"] = id_to_title.get(fields["parent"], fields["parent"])
            removed_tasks.append({
                "title": task["title"],
                "fields": fields
            })
    
    # Track dependency changes needed on existing tasks
    # When we remove tasks, other tasks lose their deps to them
    # We need to tell the model to add those deps back after creating the new tasks
    dependency_changes = []
    for task in tasks:
        if task["id"] not in to_remove:
            # Check if this task depends on any of the removed tasks
            current_deps = task.get("depends_on", [])
            for dep_id in current_deps:
                if dep_id in to_remove:
                    dependency_changes.append({
                        "action": "add",
                        "task_title": task["title"],
                        "depends_on_title": id_to_title.get(dep_id)
                    })
    
    # Remove tasks
    partial["tasks"] = [t for t in tasks if t["id"] not in to_remove]
    
    # Remove dependencies on removed tasks from partial
    for task in partial["tasks"]:
        task["depends_on"] = [d for d in task.get("depends_on", []) if d not in to_remove]
    
    # Build changes dict for prompt
    changes = {
        "add_tasks": removed_tasks,
        "edit_tasks": [],
        "delete_tasks": [],
        "parent_changes": [],
        "dependency_changes": dependency_changes
    }
    
    prompt = render_prompt(changes, prompt_format, rng)
    
    return _build_case_result(
        partial, target, prompt, target_id, case_idx,
        "ADD", prompt_format,
        titles_added=[t["title"] for t in removed_tasks],
        titles_removed=[],
        titles_edited=[],
        parent_edges_changed=0,
        dependencies_changed=len(dependency_changes)
    )


def _generate_edit_case(
    target: Dict[str, Any],
    target_id: int,
    case_idx: int,
    prompt_format: str,
    rng: random.Random
) -> Dict[str, Any]:
    """Generate EDIT case - modify fields in partial, prompt to fix them."""
    partial = copy.deepcopy(target)
    tasks = partial["tasks"]
    
    if not tasks:
        return _generate_simple_edit_case(target, target_id, case_idx, prompt_format, rng)
    
    # Edit 1-3 tasks
    num_to_edit = min(len(tasks), rng.randint(1, 3))
    to_edit_indices = rng.sample(range(len(tasks)), num_to_edit)
    
    changes = {
        "add_tasks": [],
        "edit_tasks": [],
        "delete_tasks": [],
        "parent_changes": [],
        "dependency_changes": []
    }
    
    editable_fields = ["priority", "status", "state", "impact_size"]
    
    for idx in to_edit_indices:
        task = tasks[idx]
        target_task = _get_task_by_id(target["tasks"], task["id"])
        if not target_task:
            continue
            
        title = task["title"]
        
        # Pick 1-2 fields to change
        num_fields = rng.randint(1, 2)
        fields_to_change = rng.sample(editable_fields, min(num_fields, len(editable_fields)))
        
        field_changes = {}
        for field in fields_to_change:
            original = target_task.get(field)
            
            if field == "priority":
                options = ["Critical", "High", "Medium", "Low"]
                wrong = rng.choice([o for o in options if o != original] or options)
                task[field] = wrong
                field_changes[field] = original
            elif field == "status":
                options = ["Not started", "In progress", "Blocked", "Done"]
                wrong = rng.choice([o for o in options if o != original] or options)
                task[field] = wrong
                field_changes[field] = original
            elif field == "state":
                options = ["DRAFT", "ACTIVE", "REJECTED", "ARCHIVED"]
                wrong = rng.choice([o for o in options if o != original] or options)
                task[field] = wrong
                field_changes[field] = original
            elif field == "impact_size":
                options = [1, 2, 3, 4, 5]
                wrong = rng.choice([o for o in options if o != original] or options)
                task[field] = wrong
                field_changes[field] = original
        
        if field_changes:
            changes["edit_tasks"].append({
                "title": title,
                "changes": field_changes
            })
    
    prompt = render_prompt(changes, prompt_format, rng)
    
    return _build_case_result(
        partial, target, prompt, target_id, case_idx,
        "EDIT", prompt_format,
        titles_added=[],
        titles_removed=[],
        titles_edited=[e["title"] for e in changes["edit_tasks"]],
        parent_edges_changed=0,
        dependencies_changed=0
    )


def _generate_delete_case(
    target: Dict[str, Any],
    target_id: int,
    case_idx: int,
    prompt_format: str,
    rng: random.Random
) -> Dict[str, Any]:
    """Generate DELETE case - add extra tasks to partial, prompt to delete them."""
    partial = copy.deepcopy(target)
    tasks = partial["tasks"]
    
    # Find next task ID
    existing_ids = [int(t["id"][1:]) for t in tasks if t["id"].startswith("T")]
    next_id = max(existing_ids) + 1 if existing_ids else 1
    
    # Add 1-2 extra leaf tasks
    num_extra = rng.randint(1, 2)
    extra_titles = []
    
    for i in range(num_extra):
        task_id = f"T{next_id + i}"
        title = f"Extra task to delete ({target_id}-{case_idx}-{i})"
        
        tasks.append({
            "id": task_id,
            "title": title,
            "priority": rng.choice(["Low", "Medium"]),
            "status": "Not started",
            "state": "DRAFT",
            "owner": "U_ishay",
            "created_by": "U_ishay",
            "impact_size": 1,
            "depends_on": []
        })
        extra_titles.append(title)
    
    changes = {
        "add_tasks": [],
        "edit_tasks": [],
        "delete_tasks": extra_titles,
        "parent_changes": [],
        "dependency_changes": []
    }
    
    prompt = render_prompt(changes, prompt_format, rng)
    
    return _build_case_result(
        partial, target, prompt, target_id, case_idx,
        "DELETE", prompt_format,
        titles_added=[],
        titles_removed=extra_titles,
        titles_edited=[],
        parent_edges_changed=0,
        dependencies_changed=0
    )


def _generate_parent_case(
    target: Dict[str, Any],
    target_id: int,
    case_idx: int,
    prompt_format: str,
    rng: random.Random
) -> Dict[str, Any]:
    """Generate PARENT case - modify parent relationships."""
    partial = copy.deepcopy(target)
    tasks = partial["tasks"]
    
    if len(tasks) < 3:
        return _generate_edit_case(target, target_id, case_idx, prompt_format, rng)
    
    # Build id->title map
    id_to_title = {t["id"]: t["title"] for t in target["tasks"]}
    
    # Find tasks with parents and tasks that could be new parents
    tasks_with_parents = [t for t in tasks if t.get("parent")]
    
    if not tasks_with_parents:
        return _generate_edit_case(target, target_id, case_idx, prompt_format, rng)
    
    # Change 1-2 parent relationships
    num_to_change = min(len(tasks_with_parents), rng.randint(1, 2))
    to_change = rng.sample(tasks_with_parents, num_to_change)
    
    changes = {
        "add_tasks": [],
        "edit_tasks": [],
        "delete_tasks": [],
        "parent_changes": [],
        "dependency_changes": []
    }
    
    parent_count = 0
    
    for task in to_change:
        target_task = _get_task_by_id(target["tasks"], task["id"])
        if not target_task:
            continue
        
        original_parent = target_task.get("parent")
        original_parent_title = id_to_title.get(original_parent) if original_parent else None
        
        # Set to different parent or None in partial
        if rng.random() < 0.5:
            task["parent"] = None  # Clear parent
        else:
            # Set to a different valid parent
            other_tasks = [t["id"] for t in tasks if t["id"] != task["id"] and t["id"] != original_parent]
            if other_tasks:
                task["parent"] = rng.choice(other_tasks)
        
        changes["parent_changes"].append({
            "task_title": task["title"],
            "new_parent_title": original_parent_title
        })
        parent_count += 1
    
    prompt = render_prompt(changes, prompt_format, rng)
    
    return _build_case_result(
        partial, target, prompt, target_id, case_idx,
        "PARENT", prompt_format,
        titles_added=[],
        titles_removed=[],
        titles_edited=[],
        parent_edges_changed=parent_count,
        dependencies_changed=0
    )


def _generate_dependency_case(
    target: Dict[str, Any],
    target_id: int,
    case_idx: int,
    prompt_format: str,
    rng: random.Random
) -> Dict[str, Any]:
    """Generate DEPENDENCY case - modify dependency relationships."""
    partial = copy.deepcopy(target)
    tasks = partial["tasks"]
    
    if len(tasks) < 3:
        return _generate_edit_case(target, target_id, case_idx, prompt_format, rng)
    
    # Build id->title map
    id_to_title = {t["id"]: t["title"] for t in target["tasks"]}
    
    # Find tasks with dependencies
    tasks_with_deps = [t for t in tasks if t.get("depends_on")]
    
    changes = {
        "add_tasks": [],
        "edit_tasks": [],
        "delete_tasks": [],
        "parent_changes": [],
        "dependency_changes": []
    }
    
    dep_count = 0
    
    if tasks_with_deps:
        # Remove some dependencies from partial, prompt to add them back
        num_to_change = min(len(tasks_with_deps), rng.randint(1, 2))
        to_change = rng.sample(tasks_with_deps, num_to_change)
        
        for task in to_change:
            target_task = _get_task_by_id(target["tasks"], task["id"])
            if not target_task:
                continue
            
            target_deps = target_task.get("depends_on", [])
            
            if target_deps:
                # Remove one dependency
                dep_to_remove = rng.choice(target_deps)
                if dep_to_remove in task.get("depends_on", []):
                    task["depends_on"].remove(dep_to_remove)
                    
                    changes["dependency_changes"].append({
                        "action": "add",
                        "task_title": task["title"],
                        "depends_on_title": id_to_title.get(dep_to_remove)
                    })
                    dep_count += 1
    else:
        # Add dependencies to partial that shouldn't exist, prompt to remove them
        task = rng.choice(tasks)
        other_tasks = [t["id"] for t in tasks if t["id"] != task["id"]]
        
        if other_tasks and not task.get("depends_on"):
            new_dep = rng.choice(other_tasks)
            task["depends_on"] = task.get("depends_on", []) + [new_dep]
            
            changes["dependency_changes"].append({
                "action": "remove",
                "task_title": task["title"],
                "depends_on_title": id_to_title.get(new_dep)
            })
            dep_count += 1
    
    if not changes["dependency_changes"]:
        return _generate_edit_case(target, target_id, case_idx, prompt_format, rng)
    
    prompt = render_prompt(changes, prompt_format, rng)
    
    return _build_case_result(
        partial, target, prompt, target_id, case_idx,
        "DEPENDENCY", prompt_format,
        titles_added=[],
        titles_removed=[],
        titles_edited=[],
        parent_edges_changed=0,
        dependencies_changed=dep_count
    )


def _generate_mixed_case(
    target: Dict[str, Any],
    target_id: int,
    case_idx: int,
    prompt_format: str,
    rng: random.Random
) -> Dict[str, Any]:
    """Generate MIXED case - combination of changes."""
    partial = copy.deepcopy(target)
    tasks = partial["tasks"]
    
    if len(tasks) < 3:
        return _generate_edit_case(target, target_id, case_idx, prompt_format, rng)
    
    changes = {
        "add_tasks": [],
        "edit_tasks": [],
        "delete_tasks": [],
        "parent_changes": [],
        "dependency_changes": []
    }
    
    titles_edited = []
    parent_count = 0
    dep_count = 0
    id_to_title = {t["id"]: t["title"] for t in target["tasks"]}
    
    # Edit 1 task
    task_idx = rng.randint(0, len(tasks) - 1)
    task = tasks[task_idx]
    target_task = _get_task_by_id(target["tasks"], task["id"])
    
    if target_task:
        original_priority = target_task.get("priority", "Medium")
        options = ["Critical", "High", "Medium", "Low"]
        wrong = rng.choice([o for o in options if o != original_priority] or options)
        task["priority"] = wrong
        
        changes["edit_tasks"].append({
            "title": task["title"],
            "changes": {"priority": original_priority}
        })
        titles_edited.append(task["title"])
    
    # Change 1 parent
    tasks_with_parents = [t for t in tasks if t.get("parent")]
    if tasks_with_parents:
        parent_task = rng.choice(tasks_with_parents)
        target_parent_task = _get_task_by_id(target["tasks"], parent_task["id"])
        
        if target_parent_task:
            original_parent = target_parent_task.get("parent")
            parent_task["parent"] = None
            
            changes["parent_changes"].append({
                "task_title": parent_task["title"],
                "new_parent_title": id_to_title.get(original_parent)
            })
            parent_count += 1
    
    prompt = render_prompt(changes, prompt_format, rng)
    
    return _build_case_result(
        partial, target, prompt, target_id, case_idx,
        "MIXED", prompt_format,
        titles_added=[],
        titles_removed=[],
        titles_edited=titles_edited,
        parent_edges_changed=parent_count,
        dependencies_changed=dep_count
    )


def _generate_multi_op_case(
    target: Dict[str, Any],
    target_id: int,
    case_idx: int,
    prompt_format: str,
    rng: random.Random
) -> Dict[str, Any]:
    """Generate MULTI_OP case - many operations of different types combined.
    
    This is for complex testing with 5-10+ operations including:
    - Multiple task edits
    - Multiple parent changes  
    - Multiple dependency changes
    - Task additions with cross-references
    """
    partial = copy.deepcopy(target)
    tasks = partial["tasks"]
    
    if len(tasks) < 10:
        # Need enough tasks for complex operations
        return _generate_mixed_case(target, target_id, case_idx, prompt_format, rng)
    
    changes = {
        "add_tasks": [],
        "edit_tasks": [],
        "delete_tasks": [],
        "parent_changes": [],
        "dependency_changes": []
    }
    
    titles_edited = []
    parent_count = 0
    dep_count = 0
    id_to_title = {t["id"]: t["title"] for t in target["tasks"]}
    
    # 1. Edit 3-5 tasks (various fields)
    num_edits = rng.randint(3, 5)
    task_indices = rng.sample(range(len(tasks)), min(num_edits, len(tasks)))
    
    fields_to_edit = ["priority", "status", "impact_size", "owner"]
    
    for task_idx in task_indices:
        task = tasks[task_idx]
        target_task = _get_task_by_id(target["tasks"], task["id"])
        
        if target_task:
            field = rng.choice(fields_to_edit)
            
            if field == "priority":
                original = target_task.get("priority", "Medium")
                options = ["Critical", "High", "Medium", "Low"]
                wrong = rng.choice([o for o in options if o != original] or options)
                task["priority"] = wrong
                changes["edit_tasks"].append({
                    "title": task["title"],
                    "changes": {"priority": original}
                })
            elif field == "status":
                original = target_task.get("status", "Not started")
                options = ["Not started", "In progress", "Blocked", "Done"]
                wrong = rng.choice([o for o in options if o != original] or options)
                task["status"] = wrong
                changes["edit_tasks"].append({
                    "title": task["title"],
                    "changes": {"status": original}
                })
            elif field == "impact_size":
                original = target_task.get("impact_size", 3)
                wrong = rng.choice([i for i in range(1, 6) if i != original] or [3])
                task["impact_size"] = wrong
                changes["edit_tasks"].append({
                    "title": task["title"],
                    "changes": {"impact_size": original}
                })
            elif field == "owner":
                original = target_task.get("owner", "U_ishay")
                users = list(target.get("users", {}).keys())
                if users:
                    wrong = rng.choice([u for u in users if u != original] or users)
                    task["owner"] = wrong
                    changes["edit_tasks"].append({
                        "title": task["title"],
                        "changes": {"owner": original}
                    })
            
            titles_edited.append(task["title"])
    
    # 2. Change 2-4 parents
    tasks_with_parents = [t for t in tasks if t.get("parent")]
    num_parent_changes = min(rng.randint(2, 4), len(tasks_with_parents))
    
    if tasks_with_parents and num_parent_changes > 0:
        parent_tasks_to_change = rng.sample(tasks_with_parents, num_parent_changes)
        
        for parent_task in parent_tasks_to_change:
            target_parent_task = _get_task_by_id(target["tasks"], parent_task["id"])
            
            if target_parent_task:
                original_parent = target_parent_task.get("parent")
                parent_task["parent"] = None  # Remove parent in partial
                
                changes["parent_changes"].append({
                    "task_title": parent_task["title"],
                    "new_parent_title": id_to_title.get(original_parent)
                })
                parent_count += 1
    
    # 3. Change 2-4 dependencies
    tasks_with_deps = [t for t in tasks if t.get("depends_on")]
    num_dep_changes = min(rng.randint(2, 4), len(tasks_with_deps))
    
    if tasks_with_deps and num_dep_changes > 0:
        dep_tasks_to_change = rng.sample(tasks_with_deps, num_dep_changes)
        
        for dep_task in dep_tasks_to_change:
            target_dep_task = _get_task_by_id(target["tasks"], dep_task["id"])
            
            if target_dep_task and target_dep_task.get("depends_on"):
                original_deps = target_dep_task["depends_on"]
                
                # Remove a random dependency in partial
                if dep_task.get("depends_on"):
                    removed_dep = rng.choice(dep_task["depends_on"])
                    dep_task["depends_on"] = [d for d in dep_task.get("depends_on", []) if d != removed_dep]
                    
                    changes["dependency_changes"].append({
                        "action": "add",
                        "task_title": dep_task["title"],
                        "depends_on_title": id_to_title.get(removed_dep)
                    })
                    dep_count += 1
    
    prompt = render_prompt(changes, prompt_format, rng)
    
    return _build_case_result(
        partial, target, prompt, target_id, case_idx,
        "MULTI_OP", prompt_format,
        titles_added=[],
        titles_removed=[],
        titles_edited=titles_edited,
        parent_edges_changed=parent_count,
        dependencies_changed=dep_count
    )


def _generate_ultra_mixed_case(
    target: Dict[str, Any],
    target_id: int,
    case_idx: int,
    prompt_format: str,
    rng: random.Random
) -> Dict[str, Any]:
    """Generate ULTRA_MIXED case - very complex with all operation types.
    
    This combines:
    - 2-4 task additions with parents/deps
    - 5-8 task edits (multiple fields each)
    - 1-2 task deletions
    - 4-6 parent changes
    - 4-6 dependency changes
    """
    partial = copy.deepcopy(target)
    tasks = partial["tasks"]
    
    if len(tasks) < 20:
        return _generate_multi_op_case(target, target_id, case_idx, prompt_format, rng)
    
    changes = {
        "add_tasks": [],
        "edit_tasks": [],
        "delete_tasks": [],
        "parent_changes": [],
        "dependency_changes": []
    }
    
    titles_added = []
    titles_removed = []
    titles_edited = []
    parent_count = 0
    dep_count = 0
    id_to_title = {t["id"]: t["title"] for t in target["tasks"]}
    
    # Track which tasks we've modified to avoid conflicts
    modified_task_ids = set()
    
    # 1. Remove 2-4 tasks from partial (these will be "added" back)
    num_tasks_to_add = rng.randint(2, 4)
    
    # Find leaf tasks (no children) for removal
    children = set()
    for t in tasks:
        if t.get("parent"):
            children.add(t["parent"])
    leaf_tasks = [t for t in tasks if t["id"] not in children and t["id"] not in modified_task_ids]
    
    if len(leaf_tasks) >= num_tasks_to_add:
        tasks_to_remove = rng.sample(leaf_tasks, num_tasks_to_add)
        
        for removed_task in tasks_to_remove:
            # Get target version for full info
            target_task = _get_task_by_id(target["tasks"], removed_task["id"])
            if target_task:
                # Build add_task info with fields in correct format for prompt renderer
                fields = {
                    "priority": target_task.get("priority", "Medium"),
                    "status": target_task.get("status", "Not started"),
                    "state": target_task.get("state", "ACTIVE"),
                    "impact_size": target_task.get("impact_size", 3),
                    "owner": target_task.get("owner"),
                    "created_by": target_task.get("created_by"),
                }
                
                # Add parent reference by title
                if target_task.get("parent"):
                    parent_title = id_to_title.get(target_task["parent"])
                    if parent_title:
                        fields["parent"] = parent_title
                
                # Add dependency references by title
                if target_task.get("depends_on"):
                    dep_titles = [id_to_title.get(d) for d in target_task["depends_on"] if id_to_title.get(d)]
                    if dep_titles:
                        fields["depends_on"] = dep_titles
                
                add_info = {
                    "title": target_task["title"],
                    "fields": fields
                }
                
                changes["add_tasks"].append(add_info)
                titles_added.append(target_task["title"])
                modified_task_ids.add(removed_task["id"])
        
        # Remove from partial
        partial["tasks"] = [t for t in partial["tasks"] if t["id"] not in modified_task_ids]
        tasks = partial["tasks"]
    
    # 2. Edit 5-8 tasks (various fields)
    num_edits = rng.randint(5, 8)
    available_for_edit = [t for t in tasks if t["id"] not in modified_task_ids]
    task_indices = rng.sample(range(len(available_for_edit)), min(num_edits, len(available_for_edit)))
    
    fields_to_edit = ["priority", "status", "impact_size", "owner", "state"]
    
    for idx in task_indices:
        task = available_for_edit[idx]
        target_task = _get_task_by_id(target["tasks"], task["id"])
        
        if target_task:
            # Edit 1-3 fields per task
            num_fields = rng.randint(1, 3)
            selected_fields = rng.sample(fields_to_edit, min(num_fields, len(fields_to_edit)))
            field_changes = {}
            
            for field in selected_fields:
                if field == "priority":
                    original = target_task.get("priority", "Medium")
                    options = ["Critical", "High", "Medium", "Low"]
                    wrong = rng.choice([o for o in options if o != original] or options)
                    task["priority"] = wrong
                    field_changes["priority"] = original
                elif field == "status":
                    original = target_task.get("status", "Not started")
                    options = ["Not started", "In progress", "Blocked", "Done"]
                    wrong = rng.choice([o for o in options if o != original] or options)
                    task["status"] = wrong
                    field_changes["status"] = original
                elif field == "impact_size":
                    original = target_task.get("impact_size", 3)
                    wrong = rng.choice([i for i in range(1, 6) if i != original] or [3])
                    task["impact_size"] = wrong
                    field_changes["impact_size"] = original
                elif field == "owner":
                    original = target_task.get("owner", "U_ishay")
                    users = list(target.get("users", {}).keys())
                    if users:
                        wrong = rng.choice([u for u in users if u != original] or users)
                        task["owner"] = wrong
                        field_changes["owner"] = original
                elif field == "state":
                    original = target_task.get("state", "ACTIVE")
                    options = ["DRAFT", "ACTIVE", "REJECTED", "ARCHIVED"]
                    wrong = rng.choice([o for o in options if o != original] or options)
                    task["state"] = wrong
                    field_changes["state"] = original
            
            if field_changes:
                changes["edit_tasks"].append({
                    "title": task["title"],
                    "changes": field_changes
                })
                titles_edited.append(task["title"])
                modified_task_ids.add(task["id"])
    
    # 3. Change 4-6 parents
    tasks_with_parents = [t for t in tasks if t.get("parent") and t["id"] not in modified_task_ids]
    num_parent_changes = min(rng.randint(4, 6), len(tasks_with_parents))
    
    if tasks_with_parents and num_parent_changes > 0:
        parent_tasks_to_change = rng.sample(tasks_with_parents, num_parent_changes)
        
        for parent_task in parent_tasks_to_change:
            target_parent_task = _get_task_by_id(target["tasks"], parent_task["id"])
            
            if target_parent_task:
                original_parent = target_parent_task.get("parent")
                parent_task["parent"] = None
                
                changes["parent_changes"].append({
                    "task_title": parent_task["title"],
                    "new_parent_title": id_to_title.get(original_parent)
                })
                parent_count += 1
                modified_task_ids.add(parent_task["id"])
    
    # 4. Change 4-6 dependencies
    tasks_with_deps = [t for t in tasks if t.get("depends_on") and t["id"] not in modified_task_ids]
    num_dep_changes = min(rng.randint(4, 6), len(tasks_with_deps))
    
    if tasks_with_deps and num_dep_changes > 0:
        dep_tasks_to_change = rng.sample(tasks_with_deps, num_dep_changes)
        
        for dep_task in dep_tasks_to_change:
            target_dep_task = _get_task_by_id(target["tasks"], dep_task["id"])
            
            if target_dep_task and target_dep_task.get("depends_on"):
                if dep_task.get("depends_on"):
                    removed_dep = rng.choice(dep_task["depends_on"])
                    dep_task["depends_on"] = [d for d in dep_task.get("depends_on", []) if d != removed_dep]
                    
                    changes["dependency_changes"].append({
                        "action": "add",
                        "task_title": dep_task["title"],
                        "depends_on_title": id_to_title.get(removed_dep)
                    })
                    dep_count += 1
    
    prompt = render_prompt(changes, prompt_format, rng)
    
    return _build_case_result(
        partial, target, prompt, target_id, case_idx,
        "ULTRA_MIXED", prompt_format,
        titles_added=titles_added,
        titles_removed=titles_removed,
        titles_edited=titles_edited,
        parent_edges_changed=parent_count,
        dependencies_changed=dep_count
    )


def _generate_simple_edit_case(
    target: Dict[str, Any],
    target_id: int,
    case_idx: int,
    prompt_format: str,
    rng: random.Random
) -> Dict[str, Any]:
    """Generate a simple edit case as fallback."""
    partial = copy.deepcopy(target)
    tasks = partial["tasks"]
    
    changes = {
        "add_tasks": [],
        "edit_tasks": [],
        "delete_tasks": [],
        "parent_changes": [],
        "dependency_changes": []
    }
    
    if tasks:
        task = rng.choice(tasks)
        target_task = _get_task_by_id(target["tasks"], task["id"])
        
        if target_task:
            original = target_task.get("status", "Not started")
            options = ["Not started", "In progress", "Blocked", "Done"]
            wrong = rng.choice([o for o in options if o != original] or options)
            task["status"] = wrong
            
            changes["edit_tasks"].append({
                "title": task["title"],
                "changes": {"status": original}
            })
    
    prompt = render_prompt(changes, prompt_format, rng)
    
    return _build_case_result(
        partial, target, prompt, target_id, case_idx,
        "EDIT", prompt_format,
        titles_added=[],
        titles_removed=[],
        titles_edited=[e["title"] for e in changes["edit_tasks"]],
        parent_edges_changed=0,
        dependencies_changed=0
    )


def _build_case_result(
    partial: Dict[str, Any],
    target: Dict[str, Any],
    prompt: str,
    target_id: int,
    case_idx: int,
    bucket: str,
    prompt_format: str,
    titles_added: List[str],
    titles_removed: List[str],
    titles_edited: List[str],
    parent_edges_changed: int,
    dependencies_changed: int
) -> Dict[str, Any]:
    """Build the case result dict."""
    case_id = target_id * 100 + case_idx + 1
    
    meta = {
        "case_id": f"{case_id:06d}",
        "target_id": target_id,
        "seed": target_id * 1000 + case_idx,
        "bucket": bucket,
        "prompt_format": prompt_format,
        "summary": {
            "titles_added": titles_added,
            "titles_removed": titles_removed,
            "titles_edited": titles_edited,
            "parent_edges_changed": parent_edges_changed,
            "dependencies_changed": dependencies_changed
        }
    }
    
    return {
        "partial": partial,
        "target": target,
        "prompt": prompt,
        "meta": meta
    }
