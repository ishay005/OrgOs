#!/usr/bin/env python3
"""Run a single test case offline (expects model_ops.json to exist)."""

import argparse
import json
import os
import sys

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from taskgraph_eval.executor import apply_ops, ExecutorError
from taskgraph_eval.legality import validate_state
from taskgraph_eval.compare import compare_states
from taskgraph_eval.io_utils import read_json, write_json, write_text


def main():
    parser = argparse.ArgumentParser(description="Run a single case offline")
    parser.add_argument("--case_dir", type=str, required=True,
                       help="Path to case directory")
    
    args = parser.parse_args()
    
    case_dir = args.case_dir
    
    # Check required files
    partial_path = os.path.join(case_dir, "partial.json")
    target_path = os.path.join(case_dir, "target.json")
    ops_path = os.path.join(case_dir, "model_ops.json")
    
    if not os.path.exists(ops_path):
        print(f"SKIP: {case_dir} - model_ops.json not found")
        sys.exit(0)
    
    case_id = os.path.basename(case_dir)
    
    try:
        partial = read_json(partial_path)
        target = read_json(target_path)
        ops = read_json(ops_path)
        
        # Step 1: Apply operations
        try:
            produced = apply_ops(partial, ops)
            write_json(os.path.join(case_dir, "produced.json"), produced)
        except ExecutorError as e:
            _write_failure(case_dir, case_id, f"Executor error: {e}")
            print(f"FAIL: {case_id} - Executor error: {e}")
            sys.exit(1)
        
        # Step 2: Validate produced state
        errors = validate_state(produced)
        if errors:
            error_text = "\n".join(f"[{e['path']}] {e['message']}" for e in errors)
            _write_failure(case_dir, case_id, f"Legality errors:\n{error_text}")
            print(f"FAIL: {case_id} - Produced state is illegal")
            for e in errors[:5]:
                print(f"  - [{e['path']}] {e['message']}")
            if len(errors) > 5:
                print(f"  ... and {len(errors) - 5} more errors")
            sys.exit(1)
        
        # Step 3: Compare with target
        result = compare_states(target, produced)
        
        if result.match:
            print(f"PASS: {case_id}")
            # Clean up any previous failure files
            failure_path = os.path.join(case_dir, "failure.txt")
            if os.path.exists(failure_path):
                os.remove(failure_path)
            sys.exit(0)
        else:
            diff_text = "\n".join(result.errors)
            _write_failure(case_dir, case_id, f"Comparison diff:\n{diff_text}")
            write_json(os.path.join(case_dir, "diff.json"), result.to_dict())
            print(f"FAIL: {case_id} - Comparison mismatch")
            for err in result.errors[:5]:
                print(f"  - {err}")
            if len(result.errors) > 5:
                print(f"  ... and {len(result.errors) - 5} more differences")
            sys.exit(1)
            
    except json.JSONDecodeError as e:
        _write_failure(case_dir, case_id, f"JSON parse error: {e}")
        print(f"FAIL: {case_id} - JSON parse error: {e}")
        sys.exit(1)
    except FileNotFoundError as e:
        print(f"ERROR: {case_id} - File not found: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        _write_failure(case_dir, case_id, f"Unexpected error: {e}")
        print(f"FAIL: {case_id} - Error: {e}")
        sys.exit(1)


def _write_failure(case_dir: str, case_id: str, message: str) -> None:
    """Write failure information to the case directory."""
    failure_path = os.path.join(case_dir, "failure.txt")
    write_text(failure_path, message)


if __name__ == "__main__":
    main()

