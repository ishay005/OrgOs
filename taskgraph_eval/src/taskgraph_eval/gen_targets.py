"""Target world generation - creates valid target states.

New JSON structure:
{
  "users": {...},
  "tasks": [
    {"id": "T1", "title": "...", "parent": "T2", "depends_on": ["T3"], ...}
  ]
}
"""

import random
from typing import Any, Dict, List, Set, Tuple

from .legality import validate_state


# Title templates for generating unique titles
TITLE_TEMPLATES = [
    "Implement {feature} feature",
    "Fix {component} bug",
    "Review {doc} documentation",
    "Update {system} configuration",
    "Test {module} integration",
    "Deploy {service} to production",
    "Optimize {area} performance",
    "Refactor {code} codebase",
    "Design {interface} API",
    "Migrate {data} database",
    "Validate {process} workflow",
    "Configure {tool} settings",
    "Analyze {metric} metrics",
    "Document {feature} usage",
    "Research {technology} options",
    "Create {resource} assets",
    "Setup {environment} environment",
    "Debug {issue} issue",
    "Monitor {system} health",
    "Backup {data} data",
]

FEATURES = [
    "authentication", "payment", "notification", "search", "analytics",
    "dashboard", "reporting", "export", "import", "sync", "caching",
    "logging", "monitoring", "alerting", "backup", "restore"
]

COMPONENTS = [
    "frontend", "backend", "API", "database", "cache", "queue",
    "scheduler", "worker", "gateway", "proxy", "storage"
]

PRIORITIES = ["Critical", "High", "Medium", "Low"]
STATUSES = ["Not started", "In progress", "Blocked", "Done"]
STATES = ["DRAFT", "ACTIVE", "REJECTED", "ARCHIVED"]


def generate_target(
    target_id: int,
    rng: random.Random,
    min_tasks: int = 8,
    max_tasks: int = 120
) -> Dict[str, Any]:
    """
    Generate a single valid target world.
    
    Args:
        target_id: Unique identifier for this target
        rng: Random instance for reproducibility
        min_tasks: Minimum number of tasks
        max_tasks: Maximum number of tasks
        
    Returns:
        Valid target state dict
    """
    # Determine task count based on distribution
    # 40% small (8-15), 40% medium (20-40), 20% large (60-120)
    bucket = rng.random()
    if bucket < 0.4:
        task_count = rng.randint(8, 15)
    elif bucket < 0.8:
        task_count = rng.randint(20, 40)
    else:
        task_count = rng.randint(60, min(120, max_tasks))
    
    task_count = max(min_tasks, min(task_count, max_tasks))
    
    # Create users
    users = {
        "U_ishay": {"name": "Ishay"},
        "U_elram": {"name": "Elram"}
    }
    user_ids = list(users.keys())
    
    # Generate tasks as array
    tasks: List[Dict[str, Any]] = []
    titles_used: Set[str] = set()
    
    for i in range(task_count):
        task_id = f"T{i + 1}"
        title = _generate_unique_title(target_id, i, titles_used, rng)
        titles_used.add(title)
        
        task = {
            "id": task_id,
            "title": title,
            "priority": rng.choice(PRIORITIES),
            "status": rng.choice(STATUSES),
            "state": rng.choice(["ACTIVE", "ACTIVE", "ACTIVE", "DRAFT"]),  # Bias toward ACTIVE
            "owner": rng.choice(user_ids),
            "created_by": rng.choice(user_ids),
            "impact_size": rng.randint(1, 5),
            "depends_on": [],  # Will be populated later
        }
        
        # Optionally add other fields
        if rng.random() < 0.3:
            task["perceived_owner"] = rng.choice(["Team Lead", "Developer", "Manager", "Architect"])
        if rng.random() < 0.3:
            task["main_goal"] = rng.choice([
                "Improve user experience",
                "Reduce technical debt",
                "Increase performance",
                "Enhance security",
                "Enable new features"
            ])
        if rng.random() < 0.2:
            task["resources"] = rng.choice([
                "2 developers, 1 week",
                "1 developer, 3 days",
                "Team effort, 2 sprints",
                "External contractor"
            ])
        
        tasks.append(task)
    
    # Build task index for quick lookup
    task_index = {task["id"]: i for i, task in enumerate(tasks)}
    task_ids = [task["id"] for task in tasks]
    
    # Build parent forest
    _build_parent_forest(tasks, task_index, rng)
    
    # Build dependencies (populates depends_on arrays)
    _build_dependencies(tasks, task_index, rng)
    
    state = {
        "users": users,
        "tasks": tasks
    }
    
    # Validate
    errors = validate_state(state)
    if errors:
        # This shouldn't happen with our generator, but fix if it does
        for error in errors:
            if "cycle" in error.get("message", "").lower():
                # Clear all parents and deps as a fallback
                for task in tasks:
                    task["parent"] = None
                    task["depends_on"] = []
                break
    
    return state


def _generate_unique_title(
    target_id: int,
    task_index: int,
    used: Set[str],
    rng: random.Random
) -> str:
    """Generate a unique title for a task."""
    template = rng.choice(TITLE_TEMPLATES)
    feature = rng.choice(FEATURES)
    component = rng.choice(COMPONENTS)
    
    base_title = template.format(
        feature=feature,
        component=component,
        doc=component,
        system=feature,
        module=component,
        service=feature,
        area=component,
        code=feature,
        interface=component,
        data=feature,
        process=component,
        tool=feature,
        metric=component,
        technology=feature,
        resource=component,
        environment=feature,
        issue=component
    )
    
    # Add unique suffix
    title = f"{base_title} (#{target_id}-{task_index})"
    
    # Ensure uniqueness
    counter = 0
    while title in used:
        counter += 1
        title = f"{base_title} (#{target_id}-{task_index}-{counter})"
    
    return title


def _build_parent_forest(
    tasks: List[Dict[str, Any]],
    task_index: Dict[str, int],
    rng: random.Random
) -> None:
    """Assign parent pointers to create a forest structure."""
    if len(tasks) <= 1:
        return
    
    task_ids = [task["id"] for task in tasks]
    
    # Decide how many roots (1-3)
    num_roots = min(len(task_ids), rng.randint(1, 3))
    roots = set(rng.sample(task_ids, num_roots))
    
    # Assign parents level by level to avoid cycles
    remaining = [tid for tid in task_ids if tid not in roots]
    rng.shuffle(remaining)
    
    # Level 0: roots (no parent)
    levels: List[List[str]] = [list(roots)]
    
    # Assign remaining tasks to levels
    while remaining:
        if not levels[-1]:
            break
            
        next_level_size = min(len(remaining), max(1, len(remaining) // 2))
        next_level = remaining[:next_level_size]
        remaining = remaining[next_level_size:]
        
        # Assign parents from previous level
        for tid in next_level:
            parent = rng.choice(levels[-1])
            tasks[task_index[tid]]["parent"] = parent
        
        levels.append(next_level)


def _build_dependencies(
    tasks: List[Dict[str, Any]],
    task_index: Dict[str, int],
    rng: random.Random
) -> None:
    """Build dependencies ensuring DAG property."""
    if len(tasks) <= 1:
        return
    
    task_ids = [task["id"] for task in tasks]
    
    # Create topological order to ensure DAG
    order = list(task_ids)
    rng.shuffle(order)
    order_map = {tid: i for i, tid in enumerate(order)}
    
    # Average 0-2 outgoing deps per task
    avg_deps = rng.uniform(0.5, 1.5)
    total_deps = int(len(task_ids) * avg_deps)
    
    added: Set[Tuple[str, str]] = set()
    
    for _ in range(total_deps):
        if len(added) >= len(task_ids) * 2:
            break
            
        # Pick random task
        task_id = rng.choice(task_ids)
        
        # Pick a dependency target that comes earlier in order (ensures DAG)
        candidates = [tid for tid in task_ids 
                     if tid != task_id 
                     and (task_id, tid) not in added
                     and order_map[tid] < order_map[task_id]]
        
        if not candidates:
            continue
        
        depends_on_id = rng.choice(candidates)
        
        # Add to the task's depends_on array
        task = tasks[task_index[task_id]]
        if depends_on_id not in task["depends_on"]:
            task["depends_on"].append(depends_on_id)
            added.add((task_id, depends_on_id))


def generate_targets(
    num_targets: int,
    seed: int
) -> List[Dict[str, Any]]:
    """
    Generate multiple target worlds.
    
    Args:
        num_targets: Number of targets to generate
        seed: Random seed for reproducibility
        
    Returns:
        List of target states
    """
    rng = random.Random(seed)
    targets = []
    
    for i in range(num_targets):
        target = generate_target(i + 1, rng)
        targets.append(target)
    
    return targets


def generate_complex_target(
    target_id: int,
    rng: random.Random,
    min_tasks: int = 40,
    max_tasks: int = 80,
    min_users: int = 4
) -> Dict[str, Any]:
    """
    Generate a complex target world with:
    - More tasks (40-80 default, configurable)
    - Deeper parent hierarchies (up to 5 levels)
    - More dependencies (2-4 avg per task)
    - More varied states (more DRAFT/REJECTED/ARCHIVED)
    - More optional fields populated
    """
    # Complex targets have configurable task count
    task_count = rng.randint(min_tasks, max_tasks)
    
    # Create users based on min_users
    base_users = [
        ("U_ishay", "Ishay"), ("U_elram", "Elram"), ("U_david", "David"),
        ("U_sarah", "Sarah"), ("U_mike", "Mike"), ("U_lisa", "Lisa"),
        ("U_john", "John"), ("U_emma", "Emma"), ("U_alex", "Alex"),
        ("U_nina", "Nina"), ("U_tom", "Tom"), ("U_kate", "Kate"),
        ("U_sam", "Sam"), ("U_amy", "Amy"), ("U_ben", "Ben")
    ]
    users = {uid: {"name": name} for uid, name in base_users[:max(min_users, 4)]}
    user_ids = list(users.keys())
    
    # Generate tasks as array
    tasks: List[Dict[str, Any]] = []
    titles_used: Set[str] = set()
    
    for i in range(task_count):
        task_id = f"T{i + 1}"
        title = _generate_unique_title(target_id, i, titles_used, rng)
        titles_used.add(title)
        
        # More varied state distribution for complex targets
        state = rng.choices(
            STATES,
            weights=[25, 50, 10, 15],  # DRAFT 25%, ACTIVE 50%, REJECTED 10%, ARCHIVED 15%
            k=1
        )[0]
        
        task = {
            "id": task_id,
            "title": title,
            "priority": rng.choice(PRIORITIES),
            "status": rng.choice(STATUSES),
            "state": state,
            "owner": rng.choice(user_ids),
            "created_by": rng.choice(user_ids),
            "impact_size": rng.randint(1, 5),
            "depends_on": [],
        }
        
        # More optional fields in complex mode
        if rng.random() < 0.5:
            task["perceived_owner"] = rng.choice(["Team Lead", "Developer", "Manager", "Architect", "PM", "QA"])
        if rng.random() < 0.5:
            task["main_goal"] = rng.choice([
                "Improve user experience",
                "Reduce technical debt",
                "Increase performance",
                "Enhance security",
                "Enable new features",
                "Scale infrastructure",
                "Automate workflows",
                "Migrate legacy systems"
            ])
        if rng.random() < 0.4:
            task["resources"] = rng.choice([
                "2 developers, 1 week",
                "1 developer, 3 days",
                "Team effort, 2 sprints",
                "External contractor",
                "Cross-team collaboration",
                "3 developers, 2 weeks"
            ])
        
        tasks.append(task)
    
    # Build task index
    task_index = {task["id"]: i for i, task in enumerate(tasks)}
    
    # Build deeper parent hierarchy
    _build_deep_parent_forest(tasks, task_index, rng, max_depth=5)
    
    # Build more dependencies
    _build_complex_dependencies(tasks, task_index, rng, avg_deps=2.5)
    
    state = {
        "users": users,
        "tasks": tasks
    }
    
    # Validate and fix if needed
    errors = validate_state(state)
    if errors:
        for error in errors:
            if "cycle" in error.get("message", "").lower():
                for task in tasks:
                    task["parent"] = None
                    task["depends_on"] = []
                break
    
    return state


def _build_deep_parent_forest(
    tasks: List[Dict[str, Any]],
    task_index: Dict[str, int],
    rng: random.Random,
    max_depth: int = 5
) -> None:
    """Assign parent pointers to create a deeper forest structure."""
    if len(tasks) <= 1:
        return
    
    task_ids = [task["id"] for task in tasks]
    
    # More roots for complex structure (2-5)
    num_roots = min(len(task_ids), rng.randint(2, 5))
    roots = set(rng.sample(task_ids, num_roots))
    
    remaining = [tid for tid in task_ids if tid not in roots]
    rng.shuffle(remaining)
    
    # Build deeper levels
    levels: List[List[str]] = [list(roots)]
    
    for depth in range(max_depth):
        if not remaining:
            break
        if not levels[-1]:
            break
        
        # Distribute remaining across levels more evenly
        level_size = max(1, len(remaining) // (max_depth - depth))
        level_size = min(level_size, len(remaining))
        next_level = remaining[:level_size]
        remaining = remaining[level_size:]
        
        for tid in next_level:
            parent = rng.choice(levels[-1])
            tasks[task_index[tid]]["parent"] = parent
        
        levels.append(next_level)
    
    # Assign any remaining to random existing parents
    all_assigned = [tid for level in levels for tid in level]
    for tid in remaining:
        parent = rng.choice(all_assigned)
        tasks[task_index[tid]]["parent"] = parent


def _build_complex_dependencies(
    tasks: List[Dict[str, Any]],
    task_index: Dict[str, int],
    rng: random.Random,
    avg_deps: float = 2.5
) -> None:
    """Build more dependencies for complex targets."""
    if len(tasks) <= 1:
        return
    
    task_ids = [task["id"] for task in tasks]
    
    # Create topological order to ensure DAG
    order = list(task_ids)
    rng.shuffle(order)
    order_map = {tid: i for i, tid in enumerate(order)}
    
    # More deps in complex mode
    total_deps = int(len(task_ids) * avg_deps)
    
    added: Set[Tuple[str, str]] = set()
    
    for _ in range(total_deps):
        if len(added) >= len(task_ids) * 4:
            break
        
        task_id = rng.choice(task_ids)
        
        candidates = [tid for tid in task_ids 
                     if tid != task_id 
                     and (task_id, tid) not in added
                     and order_map[tid] < order_map[task_id]]
        
        if not candidates:
            continue
        
        depends_on_id = rng.choice(candidates)
        
        task = tasks[task_index[task_id]]
        if depends_on_id not in task["depends_on"]:
            task["depends_on"].append(depends_on_id)
            added.add((task_id, depends_on_id))


def generate_ultra_complex_target(
    target_id: int,
    rng: random.Random
) -> Dict[str, Any]:
    """
    Generate an ultra-complex target world with:
    - 10+ users
    - 100-150 tasks
    - Deep parent hierarchies (up to 7 levels)
    - High dependency density (3-5 avg per task)
    - All task states represented
    - All optional fields populated
    """
    # Ultra-complex: 100-150 tasks
    task_count = rng.randint(100, 150)
    
    # 10-15 users
    base_users = [
        ("U_ishay", "Ishay"), ("U_elram", "Elram"), ("U_david", "David"),
        ("U_sarah", "Sarah"), ("U_mike", "Mike"), ("U_lisa", "Lisa"),
        ("U_john", "John"), ("U_emma", "Emma"), ("U_alex", "Alex"),
        ("U_nina", "Nina"), ("U_tom", "Tom"), ("U_kate", "Kate"),
        ("U_sam", "Sam"), ("U_amy", "Amy"), ("U_ben", "Ben")
    ]
    num_users = rng.randint(10, 15)
    users = {uid: {"name": name} for uid, name in base_users[:num_users]}
    user_ids = list(users.keys())
    
    # Generate tasks
    tasks: List[Dict[str, Any]] = []
    titles_used: Set[str] = set()
    
    for i in range(task_count):
        task_id = f"T{i + 1}"
        title = _generate_unique_title(target_id, i, titles_used, rng)
        titles_used.add(title)
        
        # Ultra-varied state distribution
        state = rng.choices(
            STATES,
            weights=[20, 45, 15, 20],  # DRAFT 20%, ACTIVE 45%, REJECTED 15%, ARCHIVED 20%
            k=1
        )[0]
        
        task = {
            "id": task_id,
            "title": title,
            "priority": rng.choice(PRIORITIES),
            "status": rng.choice(STATUSES),
            "state": state,
            "owner": rng.choice(user_ids),
            "created_by": rng.choice(user_ids),
            "impact_size": rng.randint(1, 5),
            "depends_on": [],
        }
        
        # All optional fields populated in ultra-complex
        task["perceived_owner"] = rng.choice([
            "Team Lead", "Developer", "Manager", "Architect", "PM", "QA",
            "DevOps", "Designer", "Analyst", "Stakeholder"
        ])
        task["main_goal"] = rng.choice([
            "Improve user experience",
            "Reduce technical debt",
            "Increase performance",
            "Enhance security",
            "Enable new features",
            "Scale infrastructure",
            "Automate workflows",
            "Migrate legacy systems",
            "Improve reliability",
            "Reduce costs"
        ])
        task["resources"] = rng.choice([
            "2 developers, 1 week",
            "1 developer, 3 days",
            "Team effort, 2 sprints",
            "External contractor",
            "Cross-team collaboration",
            "3 developers, 2 weeks",
            "Full team, 1 sprint",
            "5 developers, 1 month"
        ])
        
        tasks.append(task)
    
    # Build task index
    task_index = {task["id"]: i for i, task in enumerate(tasks)}
    
    # Build very deep parent hierarchy (up to 7 levels)
    _build_deep_parent_forest(tasks, task_index, rng, max_depth=7)
    
    # Build high-density dependencies (avg 3.5 per task)
    _build_complex_dependencies(tasks, task_index, rng, avg_deps=3.5)
    
    state = {
        "users": users,
        "tasks": tasks
    }
    
    # Validate and fix if needed
    errors = validate_state(state)
    if errors:
        for error in errors:
            if "cycle" in error.get("message", "").lower():
                for task in tasks:
                    task["parent"] = None
                    task["depends_on"] = []
                break
    
    return state
