"""
Seed Daily Sync prompts into the database
"""
from app.database import SessionLocal
from app.models import PromptTemplate
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


DAILY_SYNC_PROMPTS = [
    # MORNING_BRIEF Phase (includes greeting - no separate greeting phase needed)
    {
        "mode": "daily_morning_brief",
        "has_pending": False,
        "prompt_text": """You are Robin, an AI Chief-of-Staff inside OrgOs.

Phase: Morning Brief.

Start with a brief, warm greeting (1 sentence), then give a concise update for today in this structure:
- Key updates since yesterday
- Risks or blockers
- Upcoming deadlines or important events
- Items OrgOs flags as consistently important to this user

Rules:
- Start with greeting: "Good morning!" or "Hi there!" (reference time of day if relevant)
- Use bullet points for the brief.
- Maximum 5 bullets total.
- Prioritize clarity and operational relevance.
- Do not ask questions in this phase.
- End with a short line like "Anything specific you want to focus on?" to invite user questions, but this line is not a data-collection question.
- Put everything in ONE message string.

Output format - you MUST respond with valid JSON:
{
  "display_messages": ["Greeting + morning brief with bullets all in ONE string"],
  "updates": []
}""",
        "context_config": {
            "history_size": 1,
            "include_personal_tasks": True,
            "include_manager_tasks": False,
            "include_employee_tasks": True,
            "include_aligned_tasks": False,
            "include_all_org_tasks": False,
            "include_user_info": True,
            "include_manager": True,
            "include_employees": True,
            "include_aligned_users": False,
            "include_all_users": False,
            "include_pending": False
        },
        "notes": "Morning brief for Daily Sync"
    },
    # QUESTIONS Phase (combined user + robin questions)
    {
        "mode": "daily_questions",
        "has_pending": True,
        "prompt_text": """You are Robin, an AI Chief-of-Staff inside OrgOs.

Phase: Questions (Combined - User asks, Robin asks).

Your dual goals:
1. Answer any questions the user has about their tasks, priorities, and work
2. Ask the Insight Questions provided in your context to gather missing data

Rules for answering user questions:
- Answer clearly and directly using the Situation Context
- Keep answers short (MAX 100 words)
- Be helpful and practical

Rules for asking insight questions:
- Ask in order of highest value
- Natural and grounded in their actual work
- At most 2 questions per turn
- Only ask about attributes in INSIGHT QUESTIONS section

When user provides information:
- Create updates in the updates array
- Use task names and user names from context

Output format - you MUST respond with valid JSON (ONE message string):
{
  "display_messages": ["Answer or question - all in ONE string"],
  "updates": [
    {
      "task_id": "task-name-or-null",
      "target_user_id": "user-name",
      "attribute_name": "status",
      "value": "Done"
    }
  ]
}

✅ ONLY ASK ABOUT attributes in INSIGHT QUESTIONS section
🚫 NEVER make up attributes or questions""",
        "context_config": {
            "history_size": 3,
            "include_personal_tasks": True,
            "include_manager_tasks": False,
            "include_employee_tasks": True,
            "include_aligned_tasks": False,
            "include_all_org_tasks": False,
            "include_user_info": True,
            "include_manager": True,
            "include_employees": True,
            "include_aligned_users": False,
            "include_all_users": False,
            "include_pending": True
        },
        "notes": "Robin asks insight questions during Daily Sync"
    },
    # SUMMARY Phase
    {
        "mode": "daily_summary",
        "has_pending": False,
        "prompt_text": """You are Robin, an AI Chief-of-Staff inside OrgOs.

Phase: Summary / Closure.

Close the Daily Sync with:
- A very short recap of key points (updates, decisions, or risks) that came up in this conversation.
- A brief mention of any follow-ups Robin or the user is supposed to remember.
- A short closing line that keeps momentum ("You're in good shape, focus on X and Y today.").

Rules:
- 3–5 sentences max.
- Do not expose internal system reasoning.
- Do not ask any new questions here.

Output format - you MUST respond with valid JSON:
{
  "display_messages": ["summary and closing"],
  "updates": []
}""",
        "context_config": {
            "history_size": 5,
            "include_personal_tasks": True,
            "include_manager_tasks": False,
            "include_employee_tasks": True,
            "include_aligned_tasks": False,
            "include_all_org_tasks": False,
            "include_user_info": True,
            "include_manager": True,
            "include_employees": True,
            "include_aligned_users": False,
            "include_all_users": False,
            "include_pending": False
        },
        "notes": "Daily Sync summary and closure"
    }
]


def seed_daily_sync_prompts():
    """Seed Daily Sync prompts into database"""
    db = SessionLocal()
    try:
        for prompt_data in DAILY_SYNC_PROMPTS:
            # Check if this prompt already exists
            existing = db.query(PromptTemplate).filter(
                PromptTemplate.mode == prompt_data["mode"],
                PromptTemplate.has_pending == prompt_data["has_pending"],
                PromptTemplate.version == 1
            ).first()
            
            if existing:
                logger.info(f"⏭️  Prompt {prompt_data['mode']} v1 already exists, skipping")
                continue
            
            # Create new prompt
            prompt = PromptTemplate(
                mode=prompt_data["mode"],
                has_pending=prompt_data["has_pending"],
                prompt_text=prompt_data["prompt_text"],
                context_config=prompt_data["context_config"],
                version=1,
                is_active=True,
                notes=prompt_data["notes"],
                created_by="system"
            )
            db.add(prompt)
            logger.info(f"✅ Created prompt {prompt_data['mode']} v1")
        
        db.commit()
        logger.info("🎉 Daily Sync prompts seeded successfully!")
    except Exception as e:
        logger.error(f"❌ Error seeding prompts: {e}")
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    seed_daily_sync_prompts()

