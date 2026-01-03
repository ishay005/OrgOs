"""State comparison using title-based mapping (tolerates different task IDs).

New JSON structure:
{
  "users": {...},
  "tasks": [
    {"id": "T1", "title": "...", "parent": "T2", "depends_on": ["T3"], ...}
  ]
}
"""

from typing import Any, Dict, List, Set, Tuple


class CompareResult:
    """Result of comparing two states."""
    
    def __init__(self):
        self.match = True
        self.errors: List[str] = []
        self.title_mapping: Dict[str, str] = {}  # target_id -> produced_id
        self.missing_titles: List[str] = []
        self.extra_titles: List[str] = []
        self.field_diffs: List[Dict[str, Any]] = []
        self.parent_diffs: List[Dict[str, Any]] = []
        self.dependency_diffs: List[Dict[str, Any]] = []
    
    def add_error(self, msg: str) -> None:
        self.match = False
        self.errors.append(msg)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "match": self.match,
            "errors": self.errors,
            "title_mapping": self.title_mapping,
            "missing_titles": self.missing_titles,
            "extra_titles": self.extra_titles,
            "field_diffs": self.field_diffs,
            "parent_diffs": self.parent_diffs,
            "dependency_diffs": self.dependency_diffs,
        }


def compare_states(
    expected: Dict[str, Any],
    actual: Dict[str, Any]
) -> CompareResult:
    """
    Compare expected (target) state with actual (produced) state.
    
    Uses title-based matching - IDs can differ as long as titles match.
    
    Args:
        expected: The target state
        actual: The produced state
        
    Returns:
        CompareResult with match status and detailed diffs
    """
    result = CompareResult()
    
    # Get tasks arrays
    expected_tasks = expected.get("tasks", [])
    actual_tasks = actual.get("tasks", [])
    
    # Build title -> task maps
    expected_by_title: Dict[str, Dict] = {}
    actual_by_title: Dict[str, Dict] = {}
    
    for task in expected_tasks:
        title = task.get("title")
        if title:
            if title in expected_by_title:
                result.add_error(f"Duplicate title in expected: {title}")
            expected_by_title[title] = task
    
    for task in actual_tasks:
        title = task.get("title")
        if title:
            if title in actual_by_title:
                result.add_error(f"Duplicate title in actual: {title}")
            actual_by_title[title] = task
    
    # Find missing and extra titles
    expected_titles = set(expected_by_title.keys())
    actual_titles = set(actual_by_title.keys())
    
    missing = expected_titles - actual_titles
    extra = actual_titles - expected_titles
    
    if missing:
        result.match = False
        result.missing_titles = sorted(missing)
        for title in missing:
            result.add_error(f"Missing task with title: {title}")
    
    if extra:
        result.match = False
        result.extra_titles = sorted(extra)
        for title in extra:
            result.add_error(f"Extra task with title: {title}")
    
    # Build mapping for common titles
    common_titles = expected_titles & actual_titles
    for title in common_titles:
        exp_id = expected_by_title[title].get("id", "")
        act_id = actual_by_title[title].get("id", "")
        result.title_mapping[exp_id] = act_id
    
    # Build ID -> title reverse lookup for both
    exp_id_to_title = {task.get("id"): task.get("title") for task in expected_tasks}
    act_id_to_title = {task.get("id"): task.get("title") for task in actual_tasks}
    
    # Compare task fields for common titles
    _compare_task_fields(
        expected_by_title, actual_by_title,
        common_titles, result
    )
    
    # Compare parent edges using title mapping
    _compare_parent_edges(
        expected_by_title, actual_by_title,
        exp_id_to_title, act_id_to_title,
        common_titles, result
    )
    
    # Compare dependencies using title mapping
    _compare_dependencies(
        expected_by_title, actual_by_title,
        exp_id_to_title, act_id_to_title,
        common_titles, result
    )
    
    return result


# Fields to compare (excluding parent and depends_on which are handled separately)
COMPARABLE_FIELDS = [
    "priority", "status", "perceived_owner", "impact_size",
    "main_goal", "resources", "owner", "created_by", "state"
]


def _compare_task_fields(
    expected_by_title: Dict[str, Dict],
    actual_by_title: Dict[str, Dict],
    common_titles: Set[str],
    result: CompareResult
) -> None:
    """Compare task fields for tasks with matching titles."""
    
    for title in sorted(common_titles):
        exp_task = expected_by_title[title]
        act_task = actual_by_title[title]
        
        for field in COMPARABLE_FIELDS:
            exp_val = exp_task.get(field)
            act_val = act_task.get(field)
            
            if exp_val != act_val:
                result.match = False
                diff = {
                    "title": title,
                    "field": field,
                    "expected": exp_val,
                    "actual": act_val
                }
                result.field_diffs.append(diff)
                result.errors.append(
                    f"Field mismatch in '{title}'.{field}: "
                    f"expected={exp_val}, actual={act_val}"
                )


def _compare_parent_edges(
    expected_by_title: Dict[str, Dict],
    actual_by_title: Dict[str, Dict],
    exp_id_to_title: Dict[str, str],
    act_id_to_title: Dict[str, str],
    common_titles: Set[str],
    result: CompareResult
) -> None:
    """Compare parent edges using title-based mapping."""
    
    for title in sorted(common_titles):
        exp_task = expected_by_title[title]
        act_task = actual_by_title[title]
        
        exp_parent_id = exp_task.get("parent")
        act_parent_id = act_task.get("parent")
        
        # Convert to parent titles
        exp_parent_title = exp_id_to_title.get(exp_parent_id) if exp_parent_id else None
        act_parent_title = act_id_to_title.get(act_parent_id) if act_parent_id else None
        
        if exp_parent_title != act_parent_title:
            result.match = False
            diff = {
                "child_title": title,
                "expected_parent": exp_parent_title,
                "actual_parent": act_parent_title
            }
            result.parent_diffs.append(diff)
            result.errors.append(
                f"Parent mismatch for '{title}': "
                f"expected='{exp_parent_title}', actual='{act_parent_title}'"
            )


def _compare_dependencies(
    expected_by_title: Dict[str, Dict],
    actual_by_title: Dict[str, Dict],
    exp_id_to_title: Dict[str, str],
    act_id_to_title: Dict[str, str],
    common_titles: Set[str],
    result: CompareResult
) -> None:
    """Compare dependencies (depends_on arrays) using title-based mapping."""
    
    for title in sorted(common_titles):
        exp_task = expected_by_title[title]
        act_task = actual_by_title[title]
        
        # Get depends_on and convert IDs to titles
        exp_deps = set()
        for dep_id in exp_task.get("depends_on", []):
            dep_title = exp_id_to_title.get(dep_id)
            if dep_title:
                exp_deps.add(dep_title)
        
        act_deps = set()
        for dep_id in act_task.get("depends_on", []):
            dep_title = act_id_to_title.get(dep_id)
            if dep_title:
                act_deps.add(dep_title)
        
        # Find missing and extra dependencies
        missing_deps = exp_deps - act_deps
        extra_deps = act_deps - exp_deps
        
        for dep_title in sorted(missing_deps):
            result.match = False
            diff = {
                "type": "missing",
                "task": title,
                "depends_on": dep_title
            }
            result.dependency_diffs.append(diff)
            result.errors.append(
                f"Missing dependency: '{title}' -> '{dep_title}'"
            )
        
        for dep_title in sorted(extra_deps):
            result.match = False
            diff = {
                "type": "extra",
                "task": title,
                "depends_on": dep_title
            }
            result.dependency_diffs.append(diff)
            result.errors.append(
                f"Extra dependency: '{title}' -> '{dep_title}'"
            )
