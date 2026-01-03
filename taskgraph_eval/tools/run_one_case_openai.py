#!/usr/bin/env python3
"""Run a single case using OpenAI Responses API."""

import argparse
import os
import sys

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from taskgraph_eval.executor import apply_ops, ExecutorError
from taskgraph_eval.legality import validate_state
from taskgraph_eval.compare import compare_states
from taskgraph_eval.io_utils import read_json, read_text, write_json, write_text
from taskgraph_eval.openai_runner import call_openai


def main():
    parser = argparse.ArgumentParser(description="Run a case using OpenAI API")
    parser.add_argument("--case_dir", type=str, default="cases/000001",
                       help="Path to case directory")
    parser.add_argument("--model", type=str, default="gpt-4o-mini",
                       help="Model to use (default: gpt-4o-mini)")
    parser.add_argument("--temperature", type=float, default=0,
                       help="Temperature (default: 0)")
    parser.add_argument("--max_output_tokens", type=int, default=2000,
                       help="Max output tokens (default: 2000)")
    
    args = parser.parse_args()
    
    case_dir = args.case_dir
    case_id = os.path.basename(case_dir)
    
    # Check required files
    partial_path = os.path.join(case_dir, "partial.json")
    target_path = os.path.join(case_dir, "target.json")
    prompt_path = os.path.join(case_dir, "prompt.txt")
    
    for path in [partial_path, target_path, prompt_path]:
        if not os.path.exists(path):
            print(f"ERROR: Missing required file: {path}")
            sys.exit(1)
    
    # Check API key
    if not os.environ.get("OPENAI_API_KEY"):
        print("ERROR: OPENAI_API_KEY environment variable not set")
        sys.exit(1)
    
    print(f"Running case: {case_id}")
    print(f"Model: {args.model}")
    print()
    
    try:
        partial = read_json(partial_path)
        target = read_json(target_path)
        prompt_text = read_text(prompt_path)
        
        # Call OpenAI
        print("Calling OpenAI API...")
        ops = call_openai(
            prompt_text=prompt_text,
            partial_json=partial,
            model=args.model,
            temperature=args.temperature,
            max_output_tokens=args.max_output_tokens
        )
        
        # Save ops
        ops_path = os.path.join(case_dir, "model_ops.json")
        write_json(ops_path, ops)
        print(f"Saved operations to: {ops_path}")
        
        # Apply operations
        print("Applying operations...")
        try:
            produced = apply_ops(partial, ops)
            write_json(os.path.join(case_dir, "produced.json"), produced)
        except ExecutorError as e:
            write_text(os.path.join(case_dir, "failure.txt"), f"Executor error: {e}")
            print(f"FAIL: Executor error: {e}")
            sys.exit(1)
        
        # Validate
        print("Validating produced state...")
        errors = validate_state(produced)
        if errors:
            error_msg = "\n".join(f"[{e['path']}] {e['message']}" for e in errors)
            write_text(os.path.join(case_dir, "failure.txt"), f"Legality errors:\n{error_msg}")
            print(f"FAIL: Produced state is illegal")
            for e in errors[:3]:
                print(f"  - {e['message']}")
            sys.exit(1)
        
        # Compare
        print("Comparing with target...")
        result = compare_states(target, produced)
        
        if result.match:
            print()
            print("=" * 40)
            print(f"PASS: {case_id}")
            print("=" * 40)
            sys.exit(0)
        else:
            write_json(os.path.join(case_dir, "diff.json"), result.to_dict())
            write_text(os.path.join(case_dir, "failure.txt"), 
                      "Comparison diff:\n" + "\n".join(result.errors))
            print()
            print("=" * 40)
            print(f"FAIL: {case_id}")
            print("Differences found:")
            for err in result.errors[:5]:
                print(f"  - {err}")
            if len(result.errors) > 5:
                print(f"  ... and {len(result.errors) - 5} more")
            print("=" * 40)
            sys.exit(1)
            
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()

