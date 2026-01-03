#!/usr/bin/env python3
"""Validate a state for legality."""

import argparse
import json
import os
import sys

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from taskgraph_eval.legality import validate_state
from taskgraph_eval.io_utils import read_json


def main():
    parser = argparse.ArgumentParser(description="Validate a state for legality")
    parser.add_argument("--state", type=str, required=True,
                       help="Path to state JSON file")
    
    args = parser.parse_args()
    
    try:
        state = read_json(args.state)
        errors = validate_state(state)
        
        if errors:
            print(f"Found {len(errors)} legality error(s):")
            for err in errors:
                print(f"  [{err['path']}] {err['message']}")
            sys.exit(1)
        else:
            print("State is valid.")
            sys.exit(0)
            
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

