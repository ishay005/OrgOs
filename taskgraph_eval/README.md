# TaskGraph Evaluation Harness

An evaluation harness for testing LLM ability to output operations that transform partial DB snapshots into target states.

## Overview

This harness:
- Generates ~5000 test cases (50 targets × 100 cases each)
- Each case has a `partial.json`, `target.json`, and `prompt.txt`
- The LLM receives the partial state + prompt and outputs operations
- Operations are applied to produce a new state
- The produced state is validated for legality and compared against the target

## Quick Start

### 1. Setup

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Generate Test Cases

```bash
python tools/generate_tests.py --seed 123 --num_targets 50 --cases_per_target 100
```

This creates 5000 test cases in the `cases/` directory.

### 3. Run Smoke Tests

```bash
python tools/smoke_tests.py
```

### 4. Run a Single Case with OpenAI

```bash
export OPENAI_API_KEY=your_key_here
python tools/run_one_case_openai.py --case_dir cases/000001
```

### 5. Run Offline Suite (after model_ops.json exists)

```bash
python tools/run_suite_offline.py --cases_dir cases
```

## State JSON Format

```json
{
  "users": {
    "U_ishay": {"name": "Ishay"},
    "U_elram": {"name": "Elram"}
  },
  "tasks": {
    "T1": {
      "title": "Task Title (UNIQUE)",
      "priority": "Critical|High|Medium|Low",
      "status": "Not started|In progress|Blocked|Done",
      "state": "DRAFT|ACTIVE|REJECTED|ARCHIVED",
      "owner": "U_ishay",
      "created_by": "U_ishay",
      "parent": "T2|null",
      "impact_size": 1-5,
      "perceived_owner": "string",
      "main_goal": "string",
      "resources": "string"
    }
  },
  "dependencies": [
    {
      "task": "T1",
      "depends_on": "T2",
      "status": "PROPOSED|CONFIRMED|REJECTED|REMOVED"
    }
  ]
}
```

## Operation Format

The LLM outputs JSON operations:

```json
{
  "ops": [
    {"op": "TASK_CREATE", "temp_id": "tmp_1", "fields": {"title": "New Task", ...}},
    {"op": "TASK_UPDATE", "id": "T1", "patch": {"priority": "High"}},
    {"op": "SET_PARENT", "child": "tmp_1", "parent": "T1"},
    {"op": "SET_DEPENDENCY", "task": "T1", "depends_on": "T2", "status": "CONFIRMED"},
    {"op": "TASK_DELETE", "id": "T3"}
  ]
}
```

Or as a raw list:

```json
[
  {"op": "TASK_CREATE", ...},
  {"op": "TASK_UPDATE", ...}
]
```

### Operation Details

| Operation | Required Fields | Description |
|-----------|----------------|-------------|
| `TASK_CREATE` | `temp_id`, `fields.title` | Create new task with temporary ID |
| `TASK_UPDATE` | `id`, `patch` | Update existing task fields |
| `SET_PARENT` | `child`, `parent` | Set parent (use `null` to remove) |
| `SET_DEPENDENCY` | `task`, `depends_on`, `status` | Upsert dependency |
| `TASK_DELETE` | `id` | Delete task (strict: no children/active deps) |

## Comparison Rules

- **IDs can differ**: Comparison uses title-based matching
- **Field comparison**: All fields are compared for matching titles
- **Parent edges**: Compared by title mapping
- **Dependencies**: Compared as set of (task_title, depends_on_title, status)

## Legality Rules

1. Titles must be unique
2. Parent pointers form a forest (no cycles)
3. Active dependencies form a DAG (no cycles)
4. References must exist (owner, created_by, parent)
5. Enums must be valid values

## Directory Structure

```
taskgraph_eval/
├── README.md
├── requirements.txt
├── src/taskgraph_eval/
│   ├── __init__.py
│   ├── executor.py         # Apply operations
│   ├── legality.py         # Validate state
│   ├── compare.py          # Title-based comparison
│   ├── canonicalize.py     # State normalization
│   ├── prompt_render.py    # Prompt formatting
│   ├── gen_targets.py      # Target generation
│   ├── gen_cases.py        # Case generation
│   └── io_utils.py         # I/O helpers
├── tools/
│   ├── generate_tests.py   # Generate test cases
│   ├── apply_ops.py        # Apply ops to partial
│   ├── validate_state.py   # Validate state legality
│   ├── compare_states.py   # Compare two states
│   ├── run_case_offline.py # Run single case offline
│   ├── run_suite_offline.py # Run all cases offline
│   ├── run_one_case_openai.py # Run with OpenAI API
│   └── smoke_tests.py      # Smoke tests
├── fixtures/targets/       # Generated targets
├── cases/                  # Generated test cases
│   └── 000001/
│       ├── partial.json
│       ├── target.json
│       ├── prompt.txt
│       ├── meta.json
│       └── model_ops.json  # Created by OpenAI tool
└── reports/
    ├── summary.json        # Suite results
    └── failures/           # Failed case artifacts
```

## CLI Tools

### generate_tests.py

```bash
python tools/generate_tests.py \
  --out_dir . \
  --seed 123 \
  --num_targets 50 \
  --cases_per_target 100
```

### apply_ops.py

```bash
python tools/apply_ops.py \
  --partial cases/000001/partial.json \
  --ops cases/000001/model_ops.json \
  --out cases/000001/produced.json
```

### validate_state.py

```bash
python tools/validate_state.py --state cases/000001/produced.json
```

### compare_states.py

```bash
python tools/compare_states.py \
  --expected cases/000001/target.json \
  --actual cases/000001/produced.json
```

### run_case_offline.py

```bash
python tools/run_case_offline.py --case_dir cases/000001
```

### run_suite_offline.py

```bash
python tools/run_suite_offline.py --cases_dir cases --limit 100
```

### run_one_case_openai.py

```bash
export OPENAI_API_KEY=your_key_here
python tools/run_one_case_openai.py \
  --case_dir cases/000001 \
  --model gpt-4o-mini \
  --temperature 0 \
  --max_output_tokens 2000
```

## Case Categories

Cases are distributed across buckets:
- **ADD (25%)**: Tasks removed from partial, prompt to add back
- **EDIT (35%)**: Fields modified in partial, prompt to fix
- **DELETE (25%)**: Extra tasks in partial, prompt to delete
- **MIXED (15%)**: Combination of above

## Prompt Formats

Prompts are rendered in 6 different styles:
- Numbered steps
- Bullet list
- Paragraph
- YAML-like
- Table
- Meeting notes

All prompts end with: `Return ONLY valid JSON. No markdown. No extra text.`

## License

MIT

