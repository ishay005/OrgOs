#!/usr/bin/env python3
"""Generate test cases for the TaskGraph evaluation harness."""

import argparse
import os
import sys

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from taskgraph_eval.gen_targets import generate_targets, generate_complex_target, generate_ultra_complex_target
from taskgraph_eval.gen_cases import generate_cases_for_target
from taskgraph_eval.io_utils import write_json, write_text, ensure_dir


def main():
    parser = argparse.ArgumentParser(description="Generate TaskGraph evaluation test cases")
    parser.add_argument("--out_dir", type=str, default=".",
                       help="Output directory (default: current dir)")
    parser.add_argument("--seed", type=int, default=123,
                       help="Random seed (default: 123)")
    parser.add_argument("--num_targets", type=int, default=50,
                       help="Number of target worlds (default: 50)")
    parser.add_argument("--cases_per_target", type=int, default=100,
                       help="Cases per target (default: 100)")
    parser.add_argument("--start_target_id", type=int, default=1,
                       help="Starting target ID (default: 1, use higher to append)")
    parser.add_argument("--complex", action="store_true",
                       help="Generate complex targets with more tasks/deps/ops")
    parser.add_argument("--ultra", action="store_true",
                       help="Generate ultra-complex targets (10+ users, 100+ tasks, 50%+ mixed ops)")
    
    args = parser.parse_args()
    
    # Setup directories
    cases_dir = os.path.join(args.out_dir, "cases")
    targets_dir = os.path.join(args.out_dir, "fixtures", "targets")
    ensure_dir(cases_dir)
    ensure_dir(targets_dir)
    
    mode = "ULTRA-COMPLEX" if args.ultra else ("COMPLEX" if args.complex else "NORMAL")
    print(f"Generating {args.num_targets} {mode} targets with {args.cases_per_target} cases each...")
    print(f"Total cases: {args.num_targets * args.cases_per_target}")
    print(f"Starting target ID: {args.start_target_id}")
    print(f"Seed: {args.seed}")
    print(f"Output: {args.out_dir}")
    print()
    
    # Generate targets
    print("Generating target worlds...")
    if args.ultra:
        import random
        rng = random.Random(args.seed)
        targets = [generate_ultra_complex_target(args.start_target_id + i, rng) for i in range(args.num_targets)]
    elif args.complex:
        import random
        rng = random.Random(args.seed)
        targets = [generate_complex_target(args.start_target_id + i, rng) for i in range(args.num_targets)]
    else:
        targets = generate_targets(args.num_targets, args.seed)
    
    # Save targets
    for i, target in enumerate(targets):
        target_id = args.start_target_id + i
        target_path = os.path.join(targets_dir, f"target_{target_id:03d}.json")
        write_json(target_path, target)
    
    print(f"Saved {len(targets)} targets to {targets_dir}")
    print()
    
    # Generate cases
    total_cases = 0
    for i, target in enumerate(targets):
        target_id = args.start_target_id + i
        target_seed = args.seed * 1000 + target_id
        
        cases = generate_cases_for_target(
            target=target,
            target_id=target_id,
            num_cases=args.cases_per_target,
            seed=target_seed,
            complex_mode=args.complex,
            ultra_mode=args.ultra
        )
        
        for case in cases:
            case_id = case["meta"]["case_id"]
            case_dir = os.path.join(cases_dir, case_id)
            ensure_dir(case_dir)
            
            write_json(os.path.join(case_dir, "partial.json"), case["partial"])
            write_json(os.path.join(case_dir, "target.json"), case["target"])
            write_text(os.path.join(case_dir, "prompt.txt"), case["prompt"])
            write_json(os.path.join(case_dir, "meta.json"), case["meta"])
            
            total_cases += 1
        
        print(f"  Target {target_id}/{args.start_target_id + args.num_targets - 1}: {len(cases)} cases generated")
    
    print()
    print(f"Generated {total_cases} total cases in {cases_dir}")
    print("Done!")


if __name__ == "__main__":
    main()

