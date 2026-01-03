#!/usr/bin/env python3
"""Run all test cases offline that have model_ops.json."""

import argparse
import json
import os
import sys
from datetime import datetime

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from taskgraph_eval.executor import apply_ops, ExecutorError
from taskgraph_eval.legality import validate_state
from taskgraph_eval.compare import compare_states
from taskgraph_eval.io_utils import read_json, write_json, write_text, ensure_dir, list_case_dirs


def main():
    parser = argparse.ArgumentParser(description="Run all cases offline")
    parser.add_argument("--cases_dir", type=str, default="cases",
                       help="Path to cases directory (default: cases)")
    parser.add_argument("--limit", type=int, default=None,
                       help="Limit number of cases to run")
    
    args = parser.parse_args()
    
    cases_dir = args.cases_dir
    reports_dir = os.path.join(os.path.dirname(cases_dir), "reports")
    failures_dir = os.path.join(reports_dir, "failures")
    ensure_dir(reports_dir)
    ensure_dir(failures_dir)
    
    case_dirs = list_case_dirs(cases_dir)
    
    # Filter to cases with model_ops.json
    runnable = []
    for case_dir in case_dirs:
        if os.path.exists(os.path.join(case_dir, "model_ops.json")):
            runnable.append(case_dir)
    
    if args.limit:
        runnable = runnable[:args.limit]
    
    print(f"Found {len(runnable)} runnable cases (with model_ops.json)")
    print()
    
    results = {
        "timestamp": datetime.now().isoformat(),
        "total": len(runnable),
        "passed": 0,
        "failed": 0,
        "skipped": len(case_dirs) - len(runnable),
        "pass_rate": 0.0,
        "failures": []
    }
    
    for i, case_dir in enumerate(runnable):
        case_id = os.path.basename(case_dir)
        
        try:
            status, message = _run_case(case_dir)
            
            if status == "PASS":
                results["passed"] += 1
                print(f"[{i+1}/{len(runnable)}] PASS: {case_id}")
            else:
                results["failed"] += 1
                results["failures"].append({
                    "case_id": case_id,
                    "message": message
                })
                print(f"[{i+1}/{len(runnable)}] FAIL: {case_id} - {message[:50]}...")
                
                # Copy failure artifacts
                failure_case_dir = os.path.join(failures_dir, case_id)
                ensure_dir(failure_case_dir)
                write_text(os.path.join(failure_case_dir, "failure.txt"), message)
                
                # Copy relevant files
                for fname in ["partial.json", "target.json", "model_ops.json", 
                             "produced.json", "diff.json", "prompt.txt"]:
                    src = os.path.join(case_dir, fname)
                    if os.path.exists(src):
                        import shutil
                        shutil.copy(src, os.path.join(failure_case_dir, fname))
                        
        except Exception as e:
            results["failed"] += 1
            results["failures"].append({
                "case_id": case_id,
                "message": str(e)
            })
            print(f"[{i+1}/{len(runnable)}] ERROR: {case_id} - {e}")
    
    # Calculate pass rate
    if results["total"] > 0:
        results["pass_rate"] = round(results["passed"] / results["total"] * 100, 2)
    
    # Write summary
    summary_path = os.path.join(reports_dir, "summary.json")
    write_json(summary_path, results)
    
    print()
    print("=" * 60)
    print(f"SUMMARY")
    print(f"  Total:   {results['total']}")
    print(f"  Passed:  {results['passed']}")
    print(f"  Failed:  {results['failed']}")
    print(f"  Skipped: {results['skipped']}")
    print(f"  Pass Rate: {results['pass_rate']}%")
    print()
    print(f"Report saved to: {summary_path}")
    
    if results["failed"] > 0:
        print(f"Failure details in: {failures_dir}")
        sys.exit(1)
    
    sys.exit(0)


def _run_case(case_dir: str) -> tuple:
    """
    Run a single case.
    
    Returns:
        (status, message) where status is "PASS" or "FAIL"
    """
    partial = read_json(os.path.join(case_dir, "partial.json"))
    target = read_json(os.path.join(case_dir, "target.json"))
    ops = read_json(os.path.join(case_dir, "model_ops.json"))
    
    # Apply operations
    try:
        produced = apply_ops(partial, ops)
        write_json(os.path.join(case_dir, "produced.json"), produced)
    except ExecutorError as e:
        return ("FAIL", f"Executor error: {e}")
    
    # Validate
    errors = validate_state(produced)
    if errors:
        return ("FAIL", f"Legality: {errors[0]['message']}")
    
    # Compare
    result = compare_states(target, produced)
    if result.match:
        return ("PASS", "")
    else:
        write_json(os.path.join(case_dir, "diff.json"), result.to_dict())
        return ("FAIL", result.errors[0] if result.errors else "Unknown diff")


if __name__ == "__main__":
    main()

