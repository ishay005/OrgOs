"""
LLM-based question generation module using OpenAI ChatGPT API

This module generates friendly, natural questions for collecting perceptions
about tasks and users.
"""
import asyncio
import logging
from typing import Optional
from pydantic import BaseModel
from openai import AsyncOpenAI, OpenAIError, APITimeoutError, RateLimitError

from app.config import settings

logger = logging.getLogger(__name__)


class QuestionContext(BaseModel):
    """Context information needed to generate a question"""
    is_followup: bool
    attribute_label: str
    attribute_description: Optional[str] = None
    attribute_type: str  # "string" | "enum" | "int" | "float" | "bool" | "date"
    allowed_values: Optional[list[str]] = None
    task_title: Optional[str] = None
    task_description: Optional[str] = None
    target_user_name: str
    previous_value: Optional[str] = None


# Initialize OpenAI client
def get_openai_client() -> AsyncOpenAI:
    """Get configured OpenAI client"""
    if not settings.openai_api_key:
        logger.warning("OpenAI API key not configured, question generation will fail")
    return AsyncOpenAI(api_key=settings.openai_api_key)


async def _call_openai_with_retry(
    client: AsyncOpenAI,
    system_prompt: str,
    user_prompt: str,
    max_retries: int = None
) -> str:
    """
    Call OpenAI API with retry logic for transient failures.
    
    Args:
        client: OpenAI client instance
        system_prompt: System message for the LLM
        user_prompt: User message for the LLM
        max_retries: Maximum retry attempts (defaults to settings)
    
    Returns:
        Generated text from the LLM
    
    Raises:
        OpenAIError: If all retries are exhausted
    """
    if max_retries is None:
        max_retries = settings.openai_max_retries
    
    last_error = None
    
    for attempt in range(max_retries):
        try:
            response = await client.chat.completions.create(
                model=settings.openai_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.7,
                max_tokens=150
            )
            
            return response.choices[0].message.content.strip()
            
        except (APITimeoutError, RateLimitError) as e:
            # Transient errors - retry with exponential backoff
            last_error = e
            wait_time = 2 ** attempt  # 1s, 2s, 4s
            logger.warning(
                f"Transient error calling OpenAI (attempt {attempt + 1}/{max_retries}): {e}. "
                f"Retrying in {wait_time}s..."
            )
            if attempt < max_retries - 1:
                await asyncio.sleep(wait_time)
            
        except OpenAIError as e:
            # Non-transient error - fail immediately
            logger.error(f"OpenAI API error: {e}")
            raise
    
    # All retries exhausted
    logger.error(f"Failed to call OpenAI after {max_retries} retries")
    raise last_error


async def generate_question(ctx: QuestionContext) -> str:
    """
    Generate a friendly question for an attribute.
    
    This creates a new question asking the user for their perception
    of an attribute value.
    
    Args:
        ctx: Question context with attribute and task information
    
    Returns:
        A friendly, direct question (1-2 sentences)
    
    Example:
        >>> ctx = QuestionContext(
        ...     is_followup=False,
        ...     attribute_label="Priority",
        ...     attribute_type="enum",
        ...     allowed_values=["Critical", "High", "Medium", "Low"],
        ...     task_title="Build user dashboard",
        ...     target_user_name="Alice"
        ... )
        >>> await generate_question(ctx)
        "What priority would you assign to Alice's task 'Build user dashboard'?"
    """
    client = get_openai_client()
    
    # Build system prompt
    system_prompt = """You are helping collect perceptions about work tasks in a team.
Generate a single, friendly question asking for someone's perception of an attribute.

Requirements:
- Keep it short (1-2 sentences max)
- Be polite and conversational
- Ask directly, no meta-explanations
- NO emojis
- If options are provided, mention them naturally"""
    
    # Build user prompt with context
    user_parts = []
    
    # Context about what we're asking
    if ctx.task_title:
        user_parts.append(f"Ask about the task: '{ctx.task_title}'")
        if ctx.task_description:
            user_parts.append(f"Task description: {ctx.task_description}")
        user_parts.append(f"Task owner: {ctx.target_user_name}")
    else:
        user_parts.append(f"Ask about the person: {ctx.target_user_name}")
    
    # Attribute information
    user_parts.append(f"Attribute: {ctx.attribute_label}")
    if ctx.attribute_description:
        user_parts.append(f"Description: {ctx.attribute_description}")
    
    # Type-specific guidance
    if ctx.attribute_type == "enum" and ctx.allowed_values:
        options_str = ", ".join(ctx.allowed_values)
        user_parts.append(f"The answer should be one of: {options_str}")
    elif ctx.attribute_type == "bool":
        user_parts.append("The answer should be yes or no")
    elif ctx.attribute_type in ["int", "float"]:
        user_parts.append("The answer should be a number")
    
    user_parts.append("\nGenerate the question:")
    user_prompt = "\n".join(user_parts)
    
    # Call OpenAI with retry
    try:
        question = await _call_openai_with_retry(client, system_prompt, user_prompt)
        logger.info(f"Generated question for attribute '{ctx.attribute_label}'")
        return question
    except Exception as e:
        # Fallback to template-based question if LLM fails
        logger.error(f"Failed to generate question via LLM: {e}. Using fallback template.")
        return _generate_fallback_question(ctx)


async def generate_followup_question(ctx: QuestionContext) -> str:
    """
    Generate a follow-up question when a previous answer exists.
    
    This asks if the previous value still holds and what changed if not.
    
    Args:
        ctx: Question context including previous_value
    
    Returns:
        A friendly follow-up question (1-2 sentences)
    
    Example:
        >>> ctx = QuestionContext(
        ...     is_followup=True,
        ...     attribute_label="Priority",
        ...     task_title="Build user dashboard",
        ...     target_user_name="Alice",
        ...     previous_value="High"
        ... )
        >>> await generate_followup_question(ctx)
        "Yesterday you said the priority of 'Build user dashboard' was High. Is that still correct?"
    """
    client = get_openai_client()
    
    # Build system prompt
    system_prompt = """You are helping track changes in perceptions about work tasks.
Generate a follow-up question that asks if a previous answer still holds.

Requirements:
- Reference the previous answer
- Ask if it's still correct or what changed
- Keep it short (1-2 sentences max)
- Be polite and conversational
- NO emojis"""
    
    # Build user prompt
    user_parts = []
    
    if ctx.task_title:
        user_parts.append(f"Task: '{ctx.task_title}'")
        user_parts.append(f"Task owner: {ctx.target_user_name}")
    else:
        user_parts.append(f"Person: {ctx.target_user_name}")
    
    user_parts.append(f"Attribute: {ctx.attribute_label}")
    user_parts.append(f"Previous answer: {ctx.previous_value}")
    
    user_parts.append("\nGenerate a follow-up question asking if this still holds:")
    user_prompt = "\n".join(user_parts)
    
    # Call OpenAI with retry
    try:
        question = await _call_openai_with_retry(client, system_prompt, user_prompt)
        logger.info(f"Generated follow-up question for attribute '{ctx.attribute_label}'")
        return question
    except Exception as e:
        # Fallback to template-based question if LLM fails
        logger.error(f"Failed to generate follow-up question via LLM: {e}. Using fallback template.")
        return _generate_fallback_followup(ctx)


def _generate_fallback_question(ctx: QuestionContext) -> str:
    """
    Generate a template-based question as fallback when LLM fails.
    This is the same logic as the original placeholder.
    """
    # Build context
    if ctx.task_title:
        context = f"for the task '{ctx.task_title}'"
    else:
        context = f"about {ctx.target_user_name}"
    
    # Question based on attribute type
    if ctx.attribute_type == "enum" and ctx.allowed_values:
        options = ", ".join(ctx.allowed_values)
        return f"What is the {ctx.attribute_label} {context}? Options: {options}."
    elif ctx.attribute_type == "bool":
        return f"{ctx.attribute_label} {context}? (Yes/No)"
    elif ctx.attribute_type in ["int", "float"]:
        return f"What is the {ctx.attribute_label} {context}? {ctx.attribute_description or ''}"
    else:
        return f"What is the {ctx.attribute_label} {context}?"


def _generate_fallback_followup(ctx: QuestionContext) -> str:
    """
    Generate a template-based follow-up question as fallback when LLM fails.
    """
    if ctx.task_title:
        context = f"for the task '{ctx.task_title}'"
    else:
        context = f"about {ctx.target_user_name}"
    
    return f"You previously said the {ctx.attribute_label} {context} was '{ctx.previous_value}'. Is that still correct? If not, what changed?"


# ============================================================================
# Helper function for backend integration
# ============================================================================

async def generate_question_from_context(
    attribute_label: str,
    attribute_description: Optional[str],
    attribute_type: str,
    allowed_values: Optional[list[str]],
    target_user_name: str,
    task_title: Optional[str] = None,
    task_description: Optional[str] = None,
    previous_value: Optional[str] = None,
    is_followup: bool = False
) -> str:
    """
    Helper function to generate a question from individual parameters.
    
    This is a convenience wrapper that backends can use directly without
    constructing a QuestionContext object.
    
    Returns:
        Generated question text
    """
    ctx = QuestionContext(
        is_followup=is_followup,
        attribute_label=attribute_label,
        attribute_description=attribute_description,
        attribute_type=attribute_type,
        allowed_values=allowed_values,
        task_title=task_title,
        task_description=task_description,
        target_user_name=target_user_name,
        previous_value=previous_value
    )
    
    if is_followup and previous_value:
        return await generate_followup_question(ctx)
    else:
        return await generate_question(ctx)


# ============================================================================
# Test/Demo functionality
# ============================================================================

async def test_generate_question():
    """
    Test function to demonstrate question generation.
    Run this to verify LLM integration is working.
    """
    print("=" * 60)
    print("Testing LLM Question Generation")
    print("=" * 60)
    
    # Test 1: Enum attribute (priority)
    print("\n1. Testing enum attribute (priority):")
    ctx1 = QuestionContext(
        is_followup=False,
        attribute_label="Priority",
        attribute_description="How important this task is right now",
        attribute_type="enum",
        allowed_values=["Critical", "High", "Medium", "Low"],
        task_title="Implement user authentication",
        task_description="Add OAuth2 authentication to the API",
        target_user_name="Alice"
    )
    q1 = await generate_question(ctx1)
    print(f"Question: {q1}")
    
    # Test 2: String attribute (main_goal)
    print("\n2. Testing string attribute (main_goal):")
    ctx2 = QuestionContext(
        is_followup=False,
        attribute_label="Main goal",
        attribute_description="In your own words, what is the main goal of this task?",
        attribute_type="string",
        task_title="Setup CI/CD pipeline",
        target_user_name="Bob"
    )
    q2 = await generate_question(ctx2)
    print(f"Question: {q2}")
    
    # Test 3: Boolean attribute
    print("\n3. Testing boolean attribute (is_blocked):")
    ctx3 = QuestionContext(
        is_followup=False,
        attribute_label="Blocked?",
        attribute_description="Is progress currently blocked?",
        attribute_type="bool",
        task_title="Database migration",
        target_user_name="Charlie"
    )
    q3 = await generate_question(ctx3)
    print(f"Question: {q3}")
    
    # Test 4: Follow-up question
    print("\n4. Testing follow-up question:")
    ctx4 = QuestionContext(
        is_followup=True,
        attribute_label="Priority",
        attribute_type="enum",
        allowed_values=["Critical", "High", "Medium", "Low"],
        task_title="Implement user authentication",
        target_user_name="Alice",
        previous_value="High"
    )
    q4 = await generate_followup_question(ctx4)
    print(f"Question: {q4}")
    
    # Test 5: Integer attribute
    print("\n5. Testing integer attribute (impact_size):")
    ctx5 = QuestionContext(
        is_followup=False,
        attribute_label="Expected impact size",
        attribute_description="Perceived impact if this succeeds (1–5)",
        attribute_type="int",
        task_title="Refactor payment system",
        target_user_name="Diana"
    )
    q5 = await generate_question(ctx5)
    print(f"Question: {q5}")
    
    # Test 6: User attribute (no task)
    print("\n6. Testing user attribute (role_title):")
    ctx6 = QuestionContext(
        is_followup=False,
        attribute_label="Role Title",
        attribute_description="User's role or job title",
        attribute_type="string",
        target_user_name="Eve"
    )
    q6 = await generate_question(ctx6)
    print(f"Question: {q6}")
    
    print("\n" + "=" * 60)
    print("Testing complete!")
    print("=" * 60)


if __name__ == "__main__":
    """
    Run this script directly to test LLM question generation.
    
    Usage:
        python -m app.services.llm_questions
    
    Make sure to set OPENAI_API_KEY in your .env file first.
    """
    import asyncio
    
    print("\n🤖 LLM Question Generation Test\n")
    print("Make sure OPENAI_API_KEY is set in your .env file!\n")
    
    asyncio.run(test_generate_question())
