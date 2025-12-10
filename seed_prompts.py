#!/usr/bin/env python3
"""
Seed initial prompt templates from current robin_orchestrator.py code
Idempotent - only seeds if table is empty
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.database import SessionLocal
from app.models import PromptTemplate
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def seed_prompts():
    """Seed initial prompts from current code"""
    db = SessionLocal()
    
    try:
        # Define all 6 prompt combinations (3 modes x 2 pending states)
        prompts = [
            # MORNING_BRIEF with pending
            {
                "mode": "morning_brief",
                "has_pending": True,
                "prompt_text": """Mode: Morning brief with pending questions.

Your goals:
1. Give this user a very short overview of today's situation over their top tasks: what's done, what's in progress, what's blocked, and what deserves attention next.
2. You may ask at most two focused follow-up questions, but only about the tasks and attributes listed in the pending items.
- If the user provides information in response, create updates for it.


Rules:
- Start with the brief (1–3 short bullet points or short paragraphs).
- Only then, if it clearly fits, embed at most two questions at the end.
- When user provides task information, create an update in the updates array.

🚫 NEVER ASK ABOUT:
- Attributes NOT in the "RELEVANT PENDING ITEMS" section

✅ ONLY ASK ABOUT attributes actually listed in RELEVANT PENDING ITEMS section with their exact names:
- priority, status, main_goal, perceived_owner, impact_size, resources

Output format - you MUST respond with valid JSON:
{
  "display_messages": ["your brief here"],
  "updates": []
}""",
                "context_config": {
                    "history_size": 2,
                    "include_tasks": True,
                    "include_pending": True,
                    "include_user_info": True,
                    "include_manager": True,
                    "include_employees": True
                }
            },
            
            # MORNING_BRIEF without pending
            {
                "mode": "morning_brief",
                "has_pending": False,
                "prompt_text": """Mode: Morning brief, no pending questions.

Your only goal is to give this user a very short overview of today's situation over their top tasks: what's done, what's in progress, what's blocked, and what deserves attention next.

Rules:
- Do not ask the user any questions.
- Be concise (1–3 short bullet points or short paragraphs).
- When user provides task information, create an update in the updates array.

Output format - you MUST respond with valid JSON:
{
  "display_messages": ["your brief here"],
  "updates": []
}""",
                "context_config": {
                    "history_size": 2,
                    "include_tasks": True,
                    "include_pending": False,
                    "include_user_info": True,
                    "include_manager": True,
                    "include_employees": True
                }
            },
            
            # USER_QUESTION with pending
            {
                "mode": "user_question",
                "has_pending": True,
                "prompt_text": """Mode: Answer user question.

⚠️ CRITICAL: If user provides task information (status, priority, goal, etc.) → ADD TO "updates" array!

Goals:
1. Answer their question clearly in MAX 100 words
2. If they gave info → create update
3. Optionally ask 1 related follow-up ONLY about attributes in "RELEVANT PENDING ITEMS"

🚫 NEVER ASK ABOUT:
- Attributes NOT in the "RELEVANT PENDING ITEMS" section

✅ ONLY ASK ABOUT attributes actually listed in RELEVANT PENDING ITEMS section with their exact names:
- priority, status, main_goal, perceived_owner, impact_size, resources

Output format - VALID JSON:
{
  "display_messages": ["your answer"],
  "updates": [{"task_id": "task-name", "target_user_id": "owner-name", "attribute_name": "status", "value": "Done"}]
}

Rules:
- Include updates ONLY when user gives information
- Empty updates [] if just answering/asking
- Use TASK NAMES and USER NAMES from context (not UUIDs!)
- task_id: exact task name from TASKS section
- target_user_id: TASK OWNER name
- To CREATE A NEW TASK: use attribute_name="create_task", task_id=null, value=task_title
- attribute_name must be EXACT: "priority", "status", "main_goal", "perceived_owner", "impact_size", "resources"
""",
                "context_config": {
                    "history_size": 3,
                    "include_tasks": True,
                    "include_pending": True,
                    "include_user_info": True,
                    "include_manager": True,
                    "include_employees": True
                }
            },
            
            # USER_QUESTION without pending
            {
                "mode": "user_question",
                "has_pending": False,
                "prompt_text": """Mode: Answer user question, no pending follow-up.

Your goal is to answer the user's question as clearly and directly as you can using the provided context.

Rules:
- Answer in MAX 100 words - be concise!
- Do not ask the user any follow-up questions.
- If you don't know something, say so briefly.
- When user provides task information (status, priority, etc.), create an update in the updates array.
- When user wants to CREATE A NEW TASK, use attribute_name="create_task" and value=task_title.

Output format - you MUST respond with valid JSON:
{
  "display_messages": ["answer"],
  "updates": [
    {
      "task_id": null,
      "target_user_id": "current-user-name",
      "attribute_name": "create_task",
      "value": "Task Title Here"
    }
  ]
}

IMPORTANT: Only include updates when the user has actually provided information. Leave updates empty if just answering questions.""",
                "context_config": {
                    "history_size": 3,
                    "include_tasks": True,
                    "include_pending": False,
                    "include_user_info": True,
                    "include_manager": True,
                    "include_employees": True
                }
            },
            
            # COLLECT_DATA with pending
            {
                "mode": "collect_data",
                "has_pending": True,
                "prompt_text": """Mode: Collect perception data for pending items.

⚠️ CRITICAL RULE: If the user provides ANY information (like "Done", "High", "Blocked", etc.), you MUST include it in the "updates" array. Never leave "updates" empty when user answers!

Your goal: Update missing/stale attributes for tasks in the pending items.

KEEP ALL RESPONSES UNDER 100 WORDS!

How to respond:
1. If ASKING a question → "updates": []
2. If user GIVES information → "updates": [{task_id, target_user_id, attribute_name, value}]

Output format - VALID JSON ONLY:
{
  "display_messages": ["your message here"],
  "updates": [{"task_id": "task-name", "target_user_id": "owner-name", "attribute_name": "status", "value": "Done"}]
}

Rules:
- NEVER say "I've updated" unless you actually include it in "updates"!
- If user says a status/priority/value → ADD TO UPDATES
- task_id: Use TASK NAME from pending items
- target_user_id: Use TASK OWNER name (from pending items "task" field or TASKS section owner)
- attribute_name EXACT options (lowercase): "status", "priority", "main_goal", "perceived_owner", "impact_size", "resources"
- 🚫 NEVER use made-up attributes not in this list!
- IMPORTANT: target_user_id is WHO THE QUESTION IS ABOUT (task owner), NOT who is answering!
- Don't use UUIDs - use actual names!
- ONLY ask about attributes shown in "PENDING ITEMS TO COLLECT" section
""",
                "context_config": {
                    "history_size": 2,
                    "include_tasks": False,
                    "include_pending": True,
                    "include_user_info": True,
                    "include_manager": False,
                    "include_employees": False
                }
            },
            
            # COLLECT_DATA without pending
            {
                "mode": "collect_data",
                "has_pending": False,
                "prompt_text": """Mode: Collect perception data, but no pending items.

There are no pending items to update for this user right now.

Rules:
- Keep response under 100 words.
- Do not ask the user any questions.
- Say briefly that everything looks up to date.

Output format - you MUST respond with valid JSON:
{
  "display_messages": ["Everything looks up to date!"],
  "updates": []
}""",
                "context_config": {
                    "history_size": 2,
                    "include_tasks": False,
                    "include_pending": False,
                    "include_user_info": True,
                    "include_manager": False,
                    "include_employees": False
                }
            }
        ]
        
        # Check if prompts already exist
        existing_count = db.query(PromptTemplate).count()
        
        if existing_count > 0:
            logger.info(f"📋 Prompts already exist ({existing_count} templates found) - skipping seed")
            logger.info("✅ Use the UI to edit prompts or clear the table to reseed")
            return
        
        logger.info("📝 Database is empty - seeding initial prompts as version 1...")
        
        # Insert new prompts
        for prompt_data in prompts:
            prompt = PromptTemplate(
                mode=prompt_data["mode"],
                has_pending=prompt_data["has_pending"],
                prompt_text=prompt_data["prompt_text"],
                context_config=prompt_data["context_config"],
                version=1,
                is_active=True,
                created_by="system",
                notes="Initial seed from code"
            )
            db.add(prompt)
            logger.info(f"Added prompt: mode={prompt.mode}, has_pending={prompt.has_pending}")
        
        db.commit()
        logger.info("✅ Successfully seeded all prompts!")
        
        # Show summary
        count = db.query(PromptTemplate).count()
        logger.info(f"📊 Total prompts in database: {count}")
        
    except Exception as e:
        logger.error(f"❌ Error seeding prompts: {e}")
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    logger.info("🌱 Seeding prompt templates...")
    seed_prompts()

