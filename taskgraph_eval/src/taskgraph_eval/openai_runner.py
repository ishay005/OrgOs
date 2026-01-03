"""OpenAI model runner for task graph operations.

JSON Structure:
{
  "users": {...},
  "tasks": [
    {"id": "T1", "title": "...", "parent": "T2", "depends_on": ["T3"], ...}
  ]
}
"""

import json
from typing import Dict, Any, Tuple

# Valid field names for task updates
VALID_FIELDS = ["title", "priority", "status", "state", "impact_size", "owner", 
                "created_by", "perceived_owner", "main_goal", "resources"]

# JSON Schema for operations response - each op type has minimal required fields
RESPONSE_JSON_SCHEMA = {
    "type": "json_schema",
    "name": "taskgraph_ops",
    "strict": True,
    "schema": {
        "type": "object",
        "properties": {
            "ops": {
                "type": "array",
                "items": {
                    "anyOf": [
                        # TASK_UPDATE: {"op": "TASK_UPDATE", "id": "T5", "field": "status", "value": "Done"}
                        {
                            "type": "object",
                            "properties": {
                                "op": {"type": "string", "const": "TASK_UPDATE"},
                                "id": {"type": "string"},
                                "field": {"type": "string"},
                                "value": {"type": ["string", "integer", "null"]}
                            },
                            "required": ["op", "id", "field", "value"],
                            "additionalProperties": False
                        },
                        # TASK_CREATE: {"op": "TASK_CREATE", "temp_id": "new1", "title": "X", "priority": "High", ...}
                        {
                            "type": "object",
                            "properties": {
                                "op": {"type": "string", "const": "TASK_CREATE"},
                                "temp_id": {"type": "string"},
                                "title": {"type": "string"},
                                "priority": {"type": ["string", "null"]},
                                "status": {"type": ["string", "null"]},
                                "state": {"type": ["string", "null"]},
                                "impact_size": {"type": ["integer", "null"]},
                                "owner": {"type": ["string", "null"]},
                                "created_by": {"type": ["string", "null"]},
                                "perceived_owner": {"type": ["string", "null"]},
                                "main_goal": {"type": ["string", "null"]},
                                "resources": {"type": ["string", "null"]},
                                "parent": {"type": ["string", "null"]},
                                "depends_on": {"type": ["array", "null"], "items": {"type": "string"}}
                            },
                            "required": ["op", "temp_id", "title", "priority", "status", "state", 
                                        "impact_size", "owner", "created_by", "perceived_owner", 
                                        "main_goal", "resources", "parent", "depends_on"],
                            "additionalProperties": False
                        },
                        # SET_PARENT: {"op": "SET_PARENT", "child": "T5", "parent": "T3"}
                        {
                            "type": "object",
                            "properties": {
                                "op": {"type": "string", "const": "SET_PARENT"},
                                "child": {"type": "string"},
                                "parent": {"type": ["string", "null"]}
                            },
                            "required": ["op", "child", "parent"],
                            "additionalProperties": False
                        },
                        # ADD_DEPENDENCY: {"op": "ADD_DEPENDENCY", "task": "T5", "depends_on": "T3"}
                        {
                            "type": "object",
                            "properties": {
                                "op": {"type": "string", "const": "ADD_DEPENDENCY"},
                                "task": {"type": "string"},
                                "depends_on": {"type": "string"}
                            },
                            "required": ["op", "task", "depends_on"],
                            "additionalProperties": False
                        },
                        # REMOVE_DEPENDENCY: {"op": "REMOVE_DEPENDENCY", "task": "T5", "depends_on": "T3"}
                        {
                            "type": "object",
                            "properties": {
                                "op": {"type": "string", "const": "REMOVE_DEPENDENCY"},
                                "task": {"type": "string"},
                                "depends_on": {"type": "string"}
                            },
                            "required": ["op", "task", "depends_on"],
                            "additionalProperties": False
                        },
                        # TASK_DELETE: {"op": "TASK_DELETE", "id": "T5"}
                        {
                            "type": "object",
                            "properties": {
                                "op": {"type": "string", "const": "TASK_DELETE"},
                                "id": {"type": "string"}
                            },
                            "required": ["op", "id"],
                            "additionalProperties": False
                        }
                    ]
                }
            }
        },
        "required": ["ops"],
        "additionalProperties": False
    }
}

SYSTEM_PROMPT = """You are a task graph operations generator.

The task graph has tasks as an array, each with "id", "title", "parent", "depends_on" (array).

CRITICAL - RESOLVING TASK REFERENCES:

1. EXISTING TASKS (in PARTIAL_JSON):
   Look up by title to find the ID.
   Example: "Research monitoring options (#1-5)" → find in PARTIAL_JSON → use "T6"

2. NEW TASKS (being created in add_tasks):
   Use temp_id references: new1, new2, new3, etc. in order they appear.
   - First task in add_tasks → new1
   - Second task in add_tasks → new2
   - Third task in add_tasks → new3
   
   If a new task depends on ANOTHER new task, use its temp_id!
   Example: add_tasks has "Task A" (new1) and "Task B" (new2) where B depends on A:
   - Task B's depends_on should be ["new1"], NOT a lookup in PARTIAL_JSON

RULES:
- For existing tasks: use their ID from PARTIAL_JSON (T5, T6, etc.)
- For new tasks: use temp_id (new1, new2, new3) based on order in add_tasks
- Cross-references between new tasks MUST use temp_ids
- TASK_UPDATE: one op per field change
- TASK_CREATE: all fields in a single op (use null for unspecified fields)

OPERATIONS:

TASK_UPDATE - update existing task field:
  {"op": "TASK_UPDATE", "id": "T5", "field": "status", "value": "Done"}

TASK_CREATE - create new task (use temp_id for self and references to other new tasks):
  {"op": "TASK_CREATE", "temp_id": "new1", "title": "Task A", ...}
  {"op": "TASK_CREATE", "temp_id": "new2", "title": "Task B", "depends_on": ["new1", "T5"], ...}

SET_PARENT - change parent:
  {"op": "SET_PARENT", "child": "T5", "parent": "T3"}

ADD_DEPENDENCY - add dependency (can use temp_id for new tasks):
  {"op": "ADD_DEPENDENCY", "task": "T5", "depends_on": "new1"}

REMOVE_DEPENDENCY - remove dependency:
  {"op": "REMOVE_DEPENDENCY", "task": "T5", "depends_on": "T3"}

TASK_DELETE - delete task:
  {"op": "TASK_DELETE", "id": "T5"}"""


def build_prompt(prompt_text: str, partial_json: Dict[str, Any]) -> Tuple[str, str]:
    """
    Build the system and user prompts for the model.
    
    Returns:
        Tuple of (system_prompt, user_content)
    """
    partial_str = json.dumps(partial_json, indent=2)
    user_content = f"""{prompt_text}

PARTIAL_JSON:
{partial_str}
"""
    return SYSTEM_PROMPT, user_content


def call_openai(
    prompt_text: str,
    partial_json: Dict[str, Any],
    model: str = "gpt-5-mini",
    max_output_tokens: int = 4000
) -> Dict[str, Any]:
    """
    Call OpenAI Responses API to get operations.
    """
    from openai import OpenAI
    
    client = OpenAI()  # Reads OPENAI_API_KEY from env
    
    system_content, user_content = build_prompt(prompt_text, partial_json)

    response = client.responses.create(
        model=model,
        input=[
            {"role": "system", "content": system_content},
            {"role": "user", "content": user_content}
        ],
        text={"format": RESPONSE_JSON_SCHEMA},
        max_output_tokens=max_output_tokens
    )
    
    output_text = response.output_text
    return json.loads(output_text)


def get_full_prompt(prompt_text: str, partial_json: Dict[str, Any]) -> str:
    """Get the full prompt for debugging/display."""
    system_content, user_content = build_prompt(prompt_text, partial_json)
    return f"""=== SYSTEM PROMPT ===
{system_content}

=== USER PROMPT ===
{user_content}"""
