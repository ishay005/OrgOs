#!/usr/bin/env python3
"""Apply operations to a partial state and produce output."""

import argparse
import json
import os
import sys

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from taskgraph_eval.executor import apply_ops, ExecutorError
from taskgraph_eval.io_utils import read_json, write_json


def main():
    parser = argparse.ArgumentParser(description="Apply operations to a partial state")
    parser.add_argument("--partial", type=str, required=True,
                       help="Path to partial.json")
    parser.add_argument("--ops", type=str, required=True,
                       help="Path to ops.json (or model_ops.json)")
    parser.add_argument("--out", type=str, required=True,
                       help="Path to write produced.json")
    
    args = parser.parse_args()
    
    try:
        partial = read_json(args.partial)
        ops = read_json(args.ops)
        
        produced = apply_ops(partial, ops)
        
        write_json(args.out, produced)
        print(f"Successfully produced: {args.out}")
        sys.exit(0)
        
    except ExecutorError as e:
        print(f"Executor error: {e}", file=sys.stderr)
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

