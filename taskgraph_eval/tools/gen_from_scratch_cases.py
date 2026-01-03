#!/usr/bin/env python3
"""
Generate test cases where partial is empty and prompt describes all tasks in free language.
"""
import os
import sys
import json
import random

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from taskgraph_eval.io_utils import read_json, write_json, write_text, ensure_dir

PROJECT_DIR = os.path.join(os.path.dirname(__file__), "..")
CASES_DIR = os.path.join(PROJECT_DIR, "cases")
TARGETS_DIR = os.path.join(PROJECT_DIR, "fixtures", "targets")

# Selected targets with varying complexity
SELECTED_TARGETS = [
    ("target_006.json", 10),   # ~10 tasks - simple
    ("target_021.json", 9),    # ~10 tasks - simple  
    ("target_001.json", 20),   # ~20 tasks - medium
    ("target_005.json", 20),   # ~20 tasks - medium
    ("target_011.json", 24),   # ~20 tasks - medium
    ("target_022.json", 40),   # ~40 tasks - complex
    ("target_023.json", 36),   # ~40 tasks - complex
    ("target_007.json", 33),   # ~40 tasks - complex
    ("target_017.json", 76),   # ~60+ tasks - very complex
    ("target_040.json", 31),   # ~40 tasks - complex
]


def generate_free_form_prompt(target: dict, rng: random.Random) -> str:
    """Generate a natural language description of all tasks to create."""
    tasks = target["tasks"]
    users = target["users"]
    
    # Intro phrases
    intros = [
        "I need you to set up the following task structure for our project:",
        "Please create a complete task graph with these tasks:",
        "Build out this project's task hierarchy as follows:",
        "We need to organize our work. Create these tasks:",
        "Set up our project management system with the following tasks:",
    ]
    
    prompt_parts = [rng.choice(intros), ""]
    
    # Group tasks by hierarchy (roots first, then children)
    task_by_id = {t["id"]: t for t in tasks}
    roots = [t for t in tasks if not t.get("parent")]
    children = [t for t in tasks if t.get("parent")]
    
    # Describe root tasks first
    if roots:
        prompt_parts.append("## Main Tasks (Top Level)")
        for task in roots:
            prompt_parts.append(describe_task_natural(task, task_by_id, users, rng))
    
    # Then describe child tasks
    if children:
        prompt_parts.append("")
        prompt_parts.append("## Sub-Tasks")
        for task in children:
            prompt_parts.append(describe_task_natural(task, task_by_id, users, rng))
    
    # Add dependency summary
    deps_tasks = [t for t in tasks if t.get("depends_on")]
    if deps_tasks:
        prompt_parts.append("")
        prompt_parts.append("## Dependencies")
        for task in deps_tasks:
            dep_titles = [task_by_id[d]["title"] for d in task["depends_on"] if d in task_by_id]
            if dep_titles:
                prompt_parts.append(f'- "{task["title"]}" depends on: {", ".join(dep_titles)}')
    
    prompt_parts.append("")
    prompt_parts.append("Create all these tasks with the exact attributes specified. Return valid JSON operations only.")
    
    return "\n".join(prompt_parts)


def describe_task_natural(task: dict, task_by_id: dict, users: dict, rng: random.Random) -> str:
    """Describe a single task in natural language."""
    templates = [
        'Create task "{title}" - {status_phrase}, owned by {owner_name}, priority {priority}, impact {impact}.',
        '"{title}": {priority} priority, {status_phrase}. Assign to {owner_name}. Impact size: {impact}.',
        'Add "{title}" ({priority}, {status_phrase}) for {owner_name}. Impact: {impact}.',
    ]
    
    owner_id = task.get("owner", "U_ishay")
    owner_name = users.get(owner_id, {}).get("name", owner_id)
    created_by_id = task.get("created_by", owner_id)
    created_by_name = users.get(created_by_id, {}).get("name", created_by_id)
    
    status_phrases = {
        "Not started": "not yet started",
        "In progress": "currently in progress",
        "Done": "already completed",
        "Blocked": "currently blocked",
    }
    status_phrase = status_phrases.get(task.get("status", "Not started"), "not started")
    
    base = rng.choice(templates).format(
        title=task["title"],
        status_phrase=status_phrase,
        owner_name=owner_name,
        priority=task.get("priority", "Medium"),
        impact=task.get("impact_size", 3),
    )
    
    extras = []
    
    # Add state info
    state = task.get("state", "ACTIVE")
    if state != "ACTIVE":
        extras.append(f"State: {state}")
    
    # Add created_by if different from owner
    if created_by_id != owner_id:
        extras.append(f"Created by {created_by_name}")
    
    # Add parent reference
    if task.get("parent"):
        parent = task_by_id.get(task["parent"])
        if parent:
            extras.append(f'Under "{parent["title"]}"')
    
    # Add optional fields naturally
    if task.get("perceived_owner"):
        extras.append(f"Perceived as {task['perceived_owner']}'s task")
    if task.get("main_goal"):
        extras.append(f"Goal: {task['main_goal']}")
    if task.get("resources"):
        extras.append(f"Resources: {task['resources']}")
    
    if extras:
        base += " " + ". ".join(extras) + "."
    
    return f"- {base}"


def create_empty_partial(target: dict) -> dict:
    """Create an empty partial with just users."""
    return {
        "users": target["users"],
        "tasks": []
    }


def generate_case(target_file: str, case_num: int, start_case_id: int) -> dict:
    """Generate a single test case."""
    target_path = os.path.join(TARGETS_DIR, target_file)
    target = read_json(target_path)
    
    # Extract target number from filename
    target_num = int(target_file.replace("target_", "").replace(".json", ""))
    
    # Case ID format: TTTTCC where TTTT is target and CC is case
    case_id = f"{start_case_id + case_num:06d}"
    
    rng = random.Random(start_case_id + case_num)
    
    # Create case directory
    case_dir = os.path.join(CASES_DIR, case_id)
    ensure_dir(case_dir)
    
    # Generate files
    partial = create_empty_partial(target)
    prompt = generate_free_form_prompt(target, rng)
    
    meta = {
        "case_id": case_id,
        "target_id": target_num,
        "seed": start_case_id + case_num,
        "bucket": "FROM_SCRATCH",
        "prompt_format": "free_form",
        "summary": {
            "titles_added": [t["title"] for t in target["tasks"]],
            "titles_removed": [],
            "titles_edited": [],
            "parent_edges_changed": sum(1 for t in target["tasks"] if t.get("parent")),
            "dependencies_changed": sum(len(t.get("depends_on", [])) for t in target["tasks"])
        }
    }
    
    # Write files
    write_json(os.path.join(case_dir, "partial.json"), partial)
    write_json(os.path.join(case_dir, "target.json"), target)
    write_text(os.path.join(case_dir, "prompt.txt"), prompt)
    write_json(os.path.join(case_dir, "meta.json"), meta)
    
    return {
        "case_id": case_id,
        "target": target_file,
        "task_count": len(target["tasks"])
    }


def main():
    # Find the next available case ID range
    # Current max is 007010, so start at 008001
    start_case_id = 8001
    
    print(f"Generating {len(SELECTED_TARGETS)} 'from scratch' test cases...")
    print(f"Starting from case ID {start_case_id:06d}")
    print()
    
    results = []
    for i, (target_file, expected_count) in enumerate(SELECTED_TARGETS):
        result = generate_case(target_file, i, start_case_id)
        results.append(result)
        print(f"  ✓ {result['case_id']}: {result['target']} ({result['task_count']} tasks)")
    
    print()
    print(f"Created {len(results)} new test cases")
    print()
    print("Task count distribution:")
    for r in sorted(results, key=lambda x: x["task_count"]):
        print(f"  {r['case_id']}: {r['task_count']} tasks")


if __name__ == "__main__":
    main()

