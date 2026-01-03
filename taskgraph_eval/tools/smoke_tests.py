#!/usr/bin/env python3
"""Smoke tests to verify the evaluation harness works correctly."""

import json
import os
import sys

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from taskgraph_eval.executor import apply_ops, ExecutorError
from taskgraph_eval.legality import validate_state
from taskgraph_eval.compare import compare_states


def test_temp_id_creation_and_reference():
    """Test that temp_id creation and SET_PARENT referencing works."""
    print("Test: temp_id creation + SET_PARENT reference...")
    
    partial = {
        "users": {"U1": {"name": "Alice"}},
        "tasks": {
            "T1": {"title": "Parent Task", "priority": "High"}
        },
        "dependencies": []
    }
    
    ops = [
        {
            "op": "TASK_CREATE",
            "temp_id": "tmp_1",
            "fields": {
                "title": "New Child Task",
                "priority": "Medium"
            }
        },
        {
            "op": "SET_PARENT",
            "child": "tmp_1",
            "parent": "T1"
        }
    ]
    
    produced = apply_ops(partial, ops)
    
    # Find the new task
    new_task = None
    new_id = None
    for tid, task in produced["tasks"].items():
        if task["title"] == "New Child Task":
            new_task = task
            new_id = tid
            break
    
    assert new_task is not None, "New task should exist"
    assert new_task["parent"] == "T1", f"Parent should be T1, got {new_task.get('parent')}"
    assert new_id.startswith("T"), f"New ID should start with T, got {new_id}"
    
    print("  PASS")
    return True


def test_legality_detects_parent_cycle():
    """Test that legality checker detects parent cycles."""
    print("Test: legality detects parent cycle...")
    
    # Create a state with a parent cycle: T1 -> T2 -> T3 -> T1
    state = {
        "users": {},
        "tasks": {
            "T1": {"title": "Task 1", "parent": "T3"},
            "T2": {"title": "Task 2", "parent": "T1"},
            "T3": {"title": "Task 3", "parent": "T2"}
        },
        "dependencies": []
    }
    
    errors = validate_state(state)
    
    cycle_errors = [e for e in errors if "cycle" in e["message"].lower()]
    assert len(cycle_errors) > 0, "Should detect parent cycle"
    
    print("  PASS")
    return True


def test_compare_tolerates_different_ids():
    """Test that comparison tolerates different IDs but same titles/structure."""
    print("Test: compare tolerates different IDs with same titles...")
    
    expected = {
        "users": {"U1": {"name": "Alice"}},
        "tasks": {
            "T1": {"title": "Task Alpha", "priority": "High"},
            "T2": {"title": "Task Beta", "priority": "Low", "parent": "T1"}
        },
        "dependencies": [
            {"task": "T2", "depends_on": "T1", "status": "CONFIRMED"}
        ]
    }
    
    # Same structure but different IDs
    actual = {
        "users": {"U1": {"name": "Alice"}},
        "tasks": {
            "T100": {"title": "Task Alpha", "priority": "High"},
            "T200": {"title": "Task Beta", "priority": "Low", "parent": "T100"}
        },
        "dependencies": [
            {"task": "T200", "depends_on": "T100", "status": "CONFIRMED"}
        ]
    }
    
    result = compare_states(expected, actual)
    
    assert result.match, f"Should match but got errors: {result.errors}"
    
    print("  PASS")
    return True


def test_compare_detects_field_mismatch():
    """Test that comparison detects field mismatches."""
    print("Test: compare detects field mismatch...")
    
    expected = {
        "users": {},
        "tasks": {
            "T1": {"title": "Task A", "priority": "High"}
        },
        "dependencies": []
    }
    
    actual = {
        "users": {},
        "tasks": {
            "T1": {"title": "Task A", "priority": "Low"}  # Different priority
        },
        "dependencies": []
    }
    
    result = compare_states(expected, actual)
    
    assert not result.match, "Should not match due to priority difference"
    assert len(result.field_diffs) > 0, "Should have field diffs"
    
    print("  PASS")
    return True


def test_strict_delete_prevents_child_deletion():
    """Test that strict delete mode prevents deleting tasks with children."""
    print("Test: strict delete prevents deletion of task with children...")
    
    partial = {
        "users": {},
        "tasks": {
            "T1": {"title": "Parent"},
            "T2": {"title": "Child", "parent": "T1"}
        },
        "dependencies": []
    }
    
    ops = [{"op": "TASK_DELETE", "id": "T1"}]
    
    try:
        apply_ops(partial, ops, delete_mode="strict")
        assert False, "Should have raised ExecutorError"
    except ExecutorError as e:
        assert "child" in str(e).lower(), f"Error should mention child: {e}"
    
    print("  PASS")
    return True


def test_strict_delete_prevents_active_dep_deletion():
    """Test that strict delete prevents deleting tasks with active dependencies."""
    print("Test: strict delete prevents deletion of task with active deps...")
    
    partial = {
        "users": {},
        "tasks": {
            "T1": {"title": "Task 1"},
            "T2": {"title": "Task 2"}
        },
        "dependencies": [
            {"task": "T2", "depends_on": "T1", "status": "CONFIRMED"}
        ]
    }
    
    ops = [{"op": "TASK_DELETE", "id": "T1"}]
    
    try:
        apply_ops(partial, ops, delete_mode="strict")
        assert False, "Should have raised ExecutorError"
    except ExecutorError as e:
        assert "dependency" in str(e).lower(), f"Error should mention dependency: {e}"
    
    print("  PASS")
    return True


def test_dependency_upsert():
    """Test that SET_DEPENDENCY does upsert correctly."""
    print("Test: SET_DEPENDENCY upsert behavior...")
    
    partial = {
        "users": {},
        "tasks": {
            "T1": {"title": "Task 1"},
            "T2": {"title": "Task 2"}
        },
        "dependencies": [
            {"task": "T2", "depends_on": "T1", "status": "PROPOSED"}
        ]
    }
    
    ops = [
        {"op": "SET_DEPENDENCY", "task": "T2", "depends_on": "T1", "status": "CONFIRMED"}
    ]
    
    produced = apply_ops(partial, ops)
    
    # Should have exactly one dependency with status CONFIRMED
    assert len(produced["dependencies"]) == 1
    assert produced["dependencies"][0]["status"] == "CONFIRMED"
    
    print("  PASS")
    return True


def test_title_uniqueness_enforcement():
    """Test that duplicate titles are rejected."""
    print("Test: title uniqueness enforcement...")
    
    partial = {
        "users": {},
        "tasks": {
            "T1": {"title": "Existing Task"}
        },
        "dependencies": []
    }
    
    ops = [
        {
            "op": "TASK_CREATE",
            "temp_id": "tmp_1",
            "fields": {"title": "Existing Task"}  # Duplicate!
        }
    ]
    
    try:
        apply_ops(partial, ops)
        assert False, "Should have raised ExecutorError for duplicate title"
    except ExecutorError as e:
        assert "duplicate" in str(e).lower() or "title" in str(e).lower()
    
    print("  PASS")
    return True


def test_ops_in_object_format():
    """Test that ops can be provided as {"ops": [...]}."""
    print("Test: ops in object format {\"ops\": [...]}...")
    
    partial = {
        "users": {},
        "tasks": {},
        "dependencies": []
    }
    
    ops = {
        "ops": [
            {
                "op": "TASK_CREATE",
                "temp_id": "tmp_1",
                "fields": {"title": "New Task"}
            }
        ]
    }
    
    produced = apply_ops(partial, ops)
    
    assert len(produced["tasks"]) == 1
    
    print("  PASS")
    return True


def main():
    print("=" * 60)
    print("TaskGraph Evaluation Harness - Smoke Tests")
    print("=" * 60)
    print()
    
    tests = [
        test_temp_id_creation_and_reference,
        test_legality_detects_parent_cycle,
        test_compare_tolerates_different_ids,
        test_compare_detects_field_mismatch,
        test_strict_delete_prevents_child_deletion,
        test_strict_delete_prevents_active_dep_deletion,
        test_dependency_upsert,
        test_title_uniqueness_enforcement,
        test_ops_in_object_format,
    ]
    
    passed = 0
    failed = 0
    
    for test in tests:
        try:
            if test():
                passed += 1
            else:
                failed += 1
        except AssertionError as e:
            print(f"  FAIL: {e}")
            failed += 1
        except Exception as e:
            print(f"  ERROR: {e}")
            failed += 1
    
    print()
    print("=" * 60)
    print(f"Results: {passed} passed, {failed} failed")
    print("=" * 60)
    
    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()

