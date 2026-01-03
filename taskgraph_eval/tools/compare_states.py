#!/usr/bin/env python3
"""Compare expected and actual states using title-based matching."""

import argparse
import json
import os
import sys

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from taskgraph_eval.compare import compare_states
from taskgraph_eval.io_utils import read_json


def main():
    parser = argparse.ArgumentParser(description="Compare two states (title-based)")
    parser.add_argument("--expected", type=str, required=True,
                       help="Path to expected (target) state")
    parser.add_argument("--actual", type=str, required=True,
                       help="Path to actual (produced) state")
    
    args = parser.parse_args()
    
    try:
        expected = read_json(args.expected)
        actual = read_json(args.actual)
        
        result = compare_states(expected, actual)
        
        if result.match:
            print("MATCH: States are equivalent (by title mapping)")
            sys.exit(0)
        else:
            print("MISMATCH: States differ")
            print()
            
            if result.missing_titles:
                print(f"Missing titles ({len(result.missing_titles)}):")
                for t in result.missing_titles:
                    print(f"  - {t}")
            
            if result.extra_titles:
                print(f"Extra titles ({len(result.extra_titles)}):")
                for t in result.extra_titles:
                    print(f"  + {t}")
            
            if result.field_diffs:
                print(f"Field differences ({len(result.field_diffs)}):")
                for d in result.field_diffs:
                    print(f"  [{d['title']}].{d['field']}: {d['expected']} != {d['actual']}")
            
            if result.parent_diffs:
                print(f"Parent differences ({len(result.parent_diffs)}):")
                for d in result.parent_diffs:
                    print(f"  [{d['child_title']}].parent: {d['expected_parent']} != {d['actual_parent']}")
            
            if result.dependency_diffs:
                print(f"Dependency differences ({len(result.dependency_diffs)}):")
                for d in result.dependency_diffs:
                    prefix = "-" if d["type"] == "missing" else "+"
                    print(f"  {prefix} {d['task']} -> {d['depends_on']} ({d['status']})")
            
            sys.exit(1)
            
    except json.JSONDecodeError as e:
        print(f"JSON parse error: {e}", file=sys.stderr)
        sys.exit(1)
    except FileNotFoundError as e:
        print(f"File not found: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

