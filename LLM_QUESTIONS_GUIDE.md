# LLM Question Generation Module Guide

## Overview

The LLM Question Generation Module uses OpenAI's ChatGPT API to create friendly, natural questions for collecting perceptions about tasks and team members.

## Features

✅ **Natural Language Questions** - Uses GPT-4 to generate conversational questions  
✅ **Context-Aware** - Considers task, user, and attribute information  
✅ **Follow-up Support** - Handles questions about changed perceptions  
✅ **Retry Logic** - Automatic retry with exponential backoff for transient failures  
✅ **Fallback Mode** - Template-based questions if LLM fails  
✅ **Type-Aware** - Adapts questions based on attribute type (enum, string, bool, etc.)  

## Setup

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

This includes `openai==1.3.7`.

### 2. Configure OpenAI API Key

Add to your `.env` file:

```bash
OPENAI_API_KEY=sk-your-api-key-here
OPENAI_MODEL=gpt-4  # or gpt-3.5-turbo for faster/cheaper
OPENAI_MAX_RETRIES=3
```

Get your API key from: https://platform.openai.com/api-keys

### 3. Verify Configuration

```bash
# Test the LLM module directly
python -m app.services.llm_questions
```

This will generate 6 sample questions and verify your API key is working.

## Usage

### Basic Usage

```python
from app.services.llm_questions import QuestionContext, generate_question

# Create context
ctx = QuestionContext(
    is_followup=False,
    attribute_label="Priority",
    attribute_description="How important this task is right now",
    attribute_type="enum",
    allowed_values=["Critical", "High", "Medium", "Low"],
    task_title="Implement user authentication",
    task_description="Add OAuth2 authentication to the API",
    target_user_name="Alice"
)

# Generate question
question = await generate_question(ctx)
print(question)
# Output: "What priority would you assign to Alice's task 'Implement user authentication'?"
```

### Follow-up Questions

```python
from app.services.llm_questions import QuestionContext, generate_followup_question

ctx = QuestionContext(
    is_followup=True,
    attribute_label="Priority",
    attribute_type="enum",
    task_title="Implement user authentication",
    target_user_name="Alice",
    previous_value="High"
)

question = await generate_followup_question(ctx)
print(question)
# Output: "Yesterday you said the priority was High. Is that still correct?"
```

### Using the Helper Function

```python
from app.services.llm_questions import generate_question_from_context

# Simpler interface - no need to create QuestionContext object
question = await generate_question_from_context(
    attribute_label="Main goal",
    attribute_description="What is the main goal of this task?",
    attribute_type="string",
    allowed_values=None,
    target_user_name="Bob",
    task_title="Setup CI/CD pipeline",
    is_followup=False
)
```

## QuestionContext Model

```python
class QuestionContext(BaseModel):
    is_followup: bool                      # Is this a follow-up question?
    attribute_label: str                   # e.g., "Priority"
    attribute_description: Optional[str]   # Additional context
    attribute_type: str                    # "string"|"enum"|"int"|"float"|"bool"|"date"
    allowed_values: Optional[list[str]]    # For enum types
    task_title: Optional[str]              # Task being asked about
    task_description: Optional[str]        # Task details
    target_user_name: str                  # Person being asked about
    previous_value: Optional[str]          # For follow-ups
```

## Backend Integration

The backend automatically uses LLM-generated questions in:

**`GET /questions/next`** - Returns questions with LLM-generated text

The integration happens in `app/routers/questions.py`:

```python
# Generate question text using LLM
question_text = await generate_question_from_context(
    attribute_label=attribute.label,
    attribute_description=attribute.description,
    attribute_type=attribute.type.value,
    allowed_values=attribute.allowed_values,
    target_user_name=task_owner.name,
    task_title=task.title,
    task_description=task.description,
    previous_value=previous_value,
    is_followup=is_stale
)

# Store in QuestionLog
question_log = QuestionLog(
    answered_by_user_id=user.id,
    target_user_id=task.owner_user_id,
    task_id=task.id,
    attribute_id=attribute.id,
    question_text=question_text
)
```

## Testing

### Manual Testing

```bash
# Test the module directly
python -m app.services.llm_questions
```

This runs 6 test cases:
1. Enum attribute (priority)
2. String attribute (main_goal)
3. Boolean attribute (is_blocked)
4. Follow-up question
5. Integer attribute (impact_size)
6. User attribute (no task)

### Integration Testing

```bash
# Start the server
uvicorn app.main:app --reload

# Get LLM-generated questions via API
curl "http://localhost:8000/questions/next?max_questions=3" \
  -H "X-User-Id: <user-id>"
```

## Retry Logic

The module includes automatic retry with exponential backoff:

- **Max retries**: 3 (configurable)
- **Backoff**: 1s, 2s, 4s
- **Retried errors**: `APITimeoutError`, `RateLimitError`
- **Non-retried errors**: Authentication errors, invalid requests

If all retries fail, the system falls back to template-based questions.

## Fallback Mode

If the LLM fails (API error, missing key, etc.), the system automatically falls back to template-based questions:

```python
# Fallback for enum
"What is the Priority for the task 'Build Feature X'? Options: Critical, High, Medium, Low."

# Fallback for follow-up
"You previously said the Priority was 'High'. Is that still correct? If not, what changed?"
```

This ensures the system continues working even if OpenAI is unavailable.

## Example Generated Questions

### Priority (Enum)
**Context**: Task "Implement user authentication" owned by Alice  
**Generated**: "What priority would you assign to Alice's task 'Implement user authentication'? The options are Critical, High, Medium, or Low."

### Main Goal (String)
**Context**: Task "Setup CI/CD pipeline" owned by Bob  
**Generated**: "In your own words, what do you think is the main goal of Bob's task 'Setup CI/CD pipeline'?"

### Is Blocked (Boolean)
**Context**: Task "Database migration" owned by Charlie  
**Generated**: "Is Charlie's task 'Database migration' currently blocked?"

### Follow-up Question
**Context**: Priority was "High" yesterday  
**Generated**: "Yesterday you indicated the priority was High. Does that still hold true, or has it changed?"

### Impact Size (Integer)
**Context**: Task "Refactor payment system" owned by Diana  
**Generated**: "On a scale of 1 to 5, what impact do you expect Diana's task 'Refactor payment system' to have if it succeeds?"

## Configuration Options

All settings in `.env`:

```bash
# Required
OPENAI_API_KEY=sk-...

# Optional (with defaults)
OPENAI_MODEL=gpt-4              # Model to use (gpt-4, gpt-3.5-turbo, etc.)
OPENAI_MAX_RETRIES=3            # Number of retry attempts
```

### Model Selection

- **gpt-4**: Best quality, slower, more expensive
- **gpt-3.5-turbo**: Good quality, faster, cheaper
- **gpt-4-turbo**: Good balance

## Error Handling

The module handles errors gracefully:

1. **Missing API Key**: Logs warning, falls back to templates
2. **Transient Errors**: Retries with backoff
3. **Rate Limits**: Retries with backoff
4. **Non-transient Errors**: Falls back to templates
5. **All Retries Exhausted**: Falls back to templates

All errors are logged for debugging.

## Performance Considerations

- **Latency**: LLM calls add ~1-3 seconds per question
- **Batching**: Questions are generated on-demand (could be optimized)
- **Caching**: Not implemented (could cache by context hash)
- **Cost**: ~$0.01-0.03 per 1000 questions (depends on model)

### Optimization Tips

1. **Use gpt-3.5-turbo** for lower latency and cost
2. **Batch question generation** if getting many questions
3. **Cache common questions** (same task/attribute combinations)
4. **Pre-generate questions** during off-peak hours

## Troubleshooting

### "OpenAI API key not configured"
→ Add `OPENAI_API_KEY` to your `.env` file

### "Rate limit exceeded"
→ System will retry automatically. Consider using gpt-3.5-turbo or increasing wait time.

### "Questions are template-based, not natural"
→ Check API key is valid and LLM calls aren't failing (check logs)

### "Slow question generation"
→ Use gpt-3.5-turbo instead of gpt-4, or implement caching

### Testing without OpenAI
→ Leave `OPENAI_API_KEY` blank - system will use fallback templates

## API Reference

### `generate_question(ctx: QuestionContext) -> str`

Generate a new question for an attribute.

**Parameters:**
- `ctx`: QuestionContext with attribute and task information

**Returns:**
- String containing the generated question (1-2 sentences)

**Raises:**
- Falls back to template on any error (never raises)

### `generate_followup_question(ctx: QuestionContext) -> str`

Generate a follow-up question when previous answer exists.

**Parameters:**
- `ctx`: QuestionContext including previous_value

**Returns:**
- String containing the follow-up question

**Raises:**
- Falls back to template on any error (never raises)

### `generate_question_from_context(...) -> str`

Convenience wrapper that accepts individual parameters instead of QuestionContext.

See function signature in code for all parameters.

## Integration Examples

### Example 1: Generate Question for New Task

```python
# Backend code
question_text = await generate_question_from_context(
    attribute_label="Status",
    attribute_description="Current state of the task",
    attribute_type="enum",
    allowed_values=["Not started", "In progress", "Blocked", "Done"],
    target_user_name="Alice",
    task_title="Build dashboard",
    task_description="Create analytics dashboard",
    is_followup=False
)
# Result: "What is the current status of Alice's task 'Build dashboard'?"
```

### Example 2: Check for Stale Answer

```python
# If answer is >1 day old, ask follow-up
if answer_age > timedelta(days=1):
    question_text = await generate_question_from_context(
        attribute_label="Priority",
        attribute_type="enum",
        allowed_values=["Critical", "High", "Medium", "Low"],
        target_user_name="Bob",
        task_title="API refactor",
        previous_value="High",
        is_followup=True
    )
    # Result: "You previously indicated the priority was High. Is that still accurate?"
```

## Next Steps

- ✅ LLM Question Generation - **DONE!**
- ⏳ Similarity Engine (Prompt 3) - Use embeddings for semantic similarity
- ⏳ Android Client (Prompt 4) - Consume the API

## Summary

The LLM Question Generation Module is production-ready and provides:
- Natural, friendly questions via GPT-4
- Automatic fallback to templates
- Retry logic for reliability
- Easy testing and integration
- Full backward compatibility

Just add your OpenAI API key and you're ready to go! 🚀

