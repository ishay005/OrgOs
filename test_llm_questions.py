#!/usr/bin/env python3
"""
Quick test script for LLM question generation.
This demonstrates the LLM module working without needing the full backend.
"""
import asyncio
from app.services.llm_questions import QuestionContext, generate_question, generate_followup_question


async def quick_test():
    """Run a quick test of the LLM question generation"""
    
    print("\n" + "="*70)
    print("🤖 Quick LLM Question Generation Test")
    print("="*70)
    
    # Test 1: Simple enum question
    print("\n📝 Test 1: Enum Attribute (Priority)")
    print("-" * 70)
    ctx1 = QuestionContext(
        is_followup=False,
        attribute_label="Priority",
        attribute_description="How important this task is right now",
        attribute_type="enum",
        allowed_values=["Critical", "High", "Medium", "Low"],
        task_title="Build payment dashboard",
        target_user_name="Sarah"
    )
    
    try:
        q1 = await generate_question(ctx1)
        print(f"✅ Generated: {q1}")
    except Exception as e:
        print(f"❌ Error: {e}")
    
    # Test 2: Free-text question
    print("\n📝 Test 2: String Attribute (Main Goal)")
    print("-" * 70)
    ctx2 = QuestionContext(
        is_followup=False,
        attribute_label="Main goal",
        attribute_description="In your own words, what is the main goal?",
        attribute_type="string",
        task_title="Refactor authentication system",
        target_user_name="Michael"
    )
    
    try:
        q2 = await generate_question(ctx2)
        print(f"✅ Generated: {q2}")
    except Exception as e:
        print(f"❌ Error: {e}")
    
    # Test 3: Follow-up question
    print("\n📝 Test 3: Follow-up Question")
    print("-" * 70)
    ctx3 = QuestionContext(
        is_followup=True,
        attribute_label="Status",
        attribute_type="enum",
        allowed_values=["Not started", "In progress", "Blocked", "Done"],
        task_title="Database migration",
        target_user_name="Alex",
        previous_value="In progress"
    )
    
    try:
        q3 = await generate_followup_question(ctx3)
        print(f"✅ Generated: {q3}")
    except Exception as e:
        print(f"❌ Error: {e}")
    
    print("\n" + "="*70)
    print("✅ Test complete!")
    print("="*70)
    print("\n💡 Tips:")
    print("  - Make sure OPENAI_API_KEY is set in your .env file")
    print("  - If questions look template-based, check your API key")
    print("  - Run full test suite: python -m app.services.llm_questions")
    print()


if __name__ == "__main__":
    asyncio.run(quick_test())

