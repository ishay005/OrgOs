"""Prompt rendering with various format styles."""

import random
from typing import Any, Dict, List, Optional


PROMPT_FORMATS = ["numbered", "bullets", "paragraph", "yaml", "table", "meeting_notes"]

FOOTER = "\n\nReturn ONLY valid JSON. No markdown. No extra text."


def render_prompt(
    changes: Dict[str, Any],
    format_style: str,
    rng: Optional[random.Random] = None
) -> str:
    """
    Render a prompt describing changes to make.
    
    Args:
        changes: Dict with keys like 'add_tasks', 'edit_tasks', 'delete_tasks',
                 'parent_changes', 'dependency_changes'
        format_style: One of PROMPT_FORMATS
        rng: Random instance for any randomization
        
    Returns:
        Formatted prompt string
    """
    if format_style == "numbered":
        return _render_numbered(changes) + FOOTER
    elif format_style == "bullets":
        return _render_bullets(changes) + FOOTER
    elif format_style == "paragraph":
        return _render_paragraph(changes) + FOOTER
    elif format_style == "yaml":
        return _render_yaml(changes) + FOOTER
    elif format_style == "table":
        return _render_table(changes) + FOOTER
    elif format_style == "meeting_notes":
        return _render_meeting_notes(changes) + FOOTER
    else:
        return _render_numbered(changes) + FOOTER


def _get_parent_change_task(pc: Dict) -> str:
    """Get task title from parent change (supports both formats)."""
    return pc.get("task_title") or pc.get("child_title", "unknown")


def _render_numbered(changes: Dict[str, Any]) -> str:
    """Numbered steps format."""
    lines = ["Please make the following changes:\n"]
    step = 1
    
    for task in changes.get("add_tasks", []):
        lines.append(f"{step}. Create a new task titled \"{task['title']}\"")
        for field, value in task.get("fields", {}).items():
            lines.append(f"   - Set {field} to: {_format_value(value)}")
        step += 1
    
    for edit in changes.get("edit_tasks", []):
        lines.append(f"{step}. Update task \"{edit['title']}\":")
        for field, value in edit.get("changes", {}).items():
            lines.append(f"   - Change {field} to: {_format_value(value)}")
        step += 1
    
    for pc in changes.get("parent_changes", []):
        child = _get_parent_change_task(pc)
        parent = pc.get("new_parent_title")
        if parent:
            lines.append(f"{step}. Set the parent of \"{child}\" to \"{parent}\"")
        else:
            lines.append(f"{step}. Remove the parent from \"{child}\" (make it a root task)")
        step += 1
    
    for dep in changes.get("dependency_changes", []):
        task = dep.get("task_title", "unknown")
        depends_on = dep.get("depends_on_title", "unknown")
        action = dep.get("action", "add")
        if action == "add":
            lines.append(f"{step}. Add dependency: \"{task}\" depends on \"{depends_on}\"")
        else:
            lines.append(f"{step}. Remove dependency: \"{task}\" no longer depends on \"{depends_on}\"")
        step += 1
    
    for title in changes.get("delete_tasks", []):
        lines.append(f"{step}. Delete the task titled \"{title}\"")
        step += 1
    
    return "\n".join(lines)


def _render_bullets(changes: Dict[str, Any]) -> str:
    """Bullet list format."""
    lines = ["Make these changes to the task graph:\n"]
    
    for task in changes.get("add_tasks", []):
        lines.append(f"• Add new task: \"{task['title']}\"")
        for field, value in task.get("fields", {}).items():
            lines.append(f"  → {field}: {_format_value(value)}")
    
    for edit in changes.get("edit_tasks", []):
        lines.append(f"• Edit task \"{edit['title']}\"")
        for field, value in edit.get("changes", {}).items():
            lines.append(f"  → {field}: {_format_value(value)}")
    
    for pc in changes.get("parent_changes", []):
        child = _get_parent_change_task(pc)
        parent = pc.get("new_parent_title")
        if parent:
            lines.append(f"• Move \"{child}\" under \"{parent}\"")
        else:
            lines.append(f"• Detach \"{child}\" from its parent")
    
    for dep in changes.get("dependency_changes", []):
        task = dep.get("task_title", "unknown")
        depends_on = dep.get("depends_on_title", "unknown")
        action = dep.get("action", "add")
        if action == "add":
            lines.append(f"• Add dependency: \"{task}\" → \"{depends_on}\"")
        else:
            lines.append(f"• Remove dependency: \"{task}\" → \"{depends_on}\"")
    
    for title in changes.get("delete_tasks", []):
        lines.append(f"• Delete task: \"{title}\"")
    
    return "\n".join(lines)


def _render_paragraph(changes: Dict[str, Any]) -> str:
    """Paragraph/prose format."""
    sentences = []
    
    add_tasks = changes.get("add_tasks", [])
    if add_tasks:
        for task in add_tasks:
            field_parts = [f"{k}={_format_value(v)}" for k, v in task.get("fields", {}).items()]
            if field_parts:
                sentences.append(
                    f"Create a new task called \"{task['title']}\" with {', '.join(field_parts)}."
                )
            else:
                sentences.append(f"Create a new task called \"{task['title']}\".")
    
    edit_tasks = changes.get("edit_tasks", [])
    if edit_tasks:
        for edit in edit_tasks:
            field_parts = [f"{k} to {_format_value(v)}" for k, v in edit.get("changes", {}).items()]
            sentences.append(
                f"For the task \"{edit['title']}\", change {' and '.join(field_parts)}."
            )
    
    parent_changes = changes.get("parent_changes", [])
    for pc in parent_changes:
        child = _get_parent_change_task(pc)
        if pc.get("new_parent_title"):
            sentences.append(
                f"Move the task \"{child}\" to be a subtask of \"{pc['new_parent_title']}\"."
            )
        else:
            sentences.append(
                f"Make \"{child}\" a root-level task by removing its parent."
            )
    
    dep_changes = changes.get("dependency_changes", [])
    for dep in dep_changes:
        task = dep.get("task_title", "unknown")
        depends_on = dep.get("depends_on_title", "unknown")
        action = dep.get("action", "add")
        if action == "add":
            sentences.append(f"Add a dependency where \"{task}\" depends on \"{depends_on}\".")
        else:
            sentences.append(f"Remove the dependency where \"{task}\" depends on \"{depends_on}\".")
    
    delete_tasks = changes.get("delete_tasks", [])
    if delete_tasks:
        titles = ", ".join(f"\"{t}\"" for t in delete_tasks)
        sentences.append(f"Delete the following tasks: {titles}.")
    
    return " ".join(sentences)


def _render_yaml(changes: Dict[str, Any]) -> str:
    """YAML-like format."""
    lines = ["changes:"]
    
    add_tasks = changes.get("add_tasks", [])
    if add_tasks:
        lines.append("  add_tasks:")
        for task in add_tasks:
            lines.append(f"    - title: \"{task['title']}\"")
            for field, value in task.get("fields", {}).items():
                lines.append(f"      {field}: {_format_value(value)}")
    
    edit_tasks = changes.get("edit_tasks", [])
    if edit_tasks:
        lines.append("  edit_tasks:")
        for edit in edit_tasks:
            lines.append(f"    - title: \"{edit['title']}\"")
            lines.append("      set:")
            for field, value in edit.get("changes", {}).items():
                lines.append(f"        {field}: {_format_value(value)}")
    
    parent_changes = changes.get("parent_changes", [])
    if parent_changes:
        lines.append("  parent_changes:")
        for pc in parent_changes:
            child = _get_parent_change_task(pc)
            lines.append(f"    - task: \"{child}\"")
            if pc.get("new_parent_title"):
                lines.append(f"      parent: \"{pc['new_parent_title']}\"")
            else:
                lines.append("      parent: null")
    
    dep_changes = changes.get("dependency_changes", [])
    if dep_changes:
        lines.append("  dependency_changes:")
        for dep in dep_changes:
            task = dep.get("task_title", "unknown")
            depends_on = dep.get("depends_on_title", "unknown")
            action = dep.get("action", "add")
            lines.append(f"    - action: {action}")
            lines.append(f"      task: \"{task}\"")
            lines.append(f"      depends_on: \"{depends_on}\"")
    
    delete_tasks = changes.get("delete_tasks", [])
    if delete_tasks:
        lines.append("  delete_tasks:")
        for title in delete_tasks:
            lines.append(f"    - \"{title}\"")
    
    return "\n".join(lines)


def _render_table(changes: Dict[str, Any]) -> str:
    """Table-like format."""
    lines = ["Requested changes:\n"]
    lines.append("| Action | Target | Details |")
    lines.append("|--------|--------|---------|")
    
    for task in changes.get("add_tasks", []):
        fields_str = "; ".join(f"{k}={_format_value(v)}" for k, v in task.get("fields", {}).items())
        lines.append(f"| CREATE | {task['title']} | {fields_str} |")
    
    for edit in changes.get("edit_tasks", []):
        fields_str = "; ".join(f"{k}→{_format_value(v)}" for k, v in edit.get("changes", {}).items())
        lines.append(f"| UPDATE | {edit['title']} | {fields_str} |")
    
    for pc in changes.get("parent_changes", []):
        child = _get_parent_change_task(pc)
        parent = pc.get("new_parent_title") or "null"
        lines.append(f"| SET_PARENT | {child} | parent={parent} |")
    
    for dep in changes.get("dependency_changes", []):
        task = dep.get("task_title", "unknown")
        depends_on = dep.get("depends_on_title", "unknown")
        action = dep.get("action", "add").upper()
        lines.append(f"| {action}_DEP | {task} → {depends_on} | - |")
    
    for title in changes.get("delete_tasks", []):
        lines.append(f"| DELETE | {title} | - |")
    
    return "\n".join(lines)


def _render_meeting_notes(changes: Dict[str, Any]) -> str:
    """Meeting notes style (informal but explicit)."""
    lines = ["MEETING NOTES - Task Updates\n"]
    lines.append("Date: Today")
    lines.append("Attendees: Team\n")
    lines.append("Action Items:\n")
    
    for task in changes.get("add_tasks", []):
        lines.append(f"[ACTION] @team needs to create new task \"{task['title']}\"")
        for field, value in task.get("fields", {}).items():
            lines.append(f"         - {field} should be: {_format_value(value)}")
        lines.append("")
    
    for edit in changes.get("edit_tasks", []):
        lines.append(f"[UPDATE] Task \"{edit['title']}\" requires changes:")
        for field, value in edit.get("changes", {}).items():
            lines.append(f"         - {field}: {_format_value(value)}")
        lines.append("")
    
    for pc in changes.get("parent_changes", []):
        child = _get_parent_change_task(pc)
        if pc.get("new_parent_title"):
            lines.append(f"[REORG] Move \"{child}\" under \"{pc['new_parent_title']}\"")
        else:
            lines.append(f"[REORG] Task \"{child}\" should be top-level (no parent)")
        lines.append("")
    
    for dep in changes.get("dependency_changes", []):
        task = dep.get("task_title", "unknown")
        depends_on = dep.get("depends_on_title", "unknown")
        action = dep.get("action", "add")
        if action == "add":
            lines.append(f"[DEPENDENCY] Add: \"{task}\" depends on \"{depends_on}\"")
        else:
            lines.append(f"[DEPENDENCY] Remove: \"{task}\" no longer depends on \"{depends_on}\"")
        lines.append("")
    
    for title in changes.get("delete_tasks", []):
        lines.append(f"[CLEANUP] Remove task \"{title}\" - no longer needed")
        lines.append("")
    
    return "\n".join(lines)


def _format_value(value: Any) -> str:
    """Format a value for display in prompt."""
    if isinstance(value, str):
        return f"\"{value}\""
    elif isinstance(value, list):
        if not value:
            return "[]"
        # Format list items nicely
        items = [f"\"{v}\"" if isinstance(v, str) else str(v) for v in value]
        return f"[{', '.join(items)}]"
    elif value is None:
        return "null"
    else:
        return str(value)
