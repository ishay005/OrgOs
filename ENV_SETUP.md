# Environment Configuration

## Required Environment Variables

Create a `.env` file in the project root with the following variables:

```bash
# Database Configuration
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/orgos

# OpenAI API Configuration (Required for LLM question generation)
OPENAI_API_KEY=your-openai-api-key-here
OPENAI_MODEL=gpt-4
OPENAI_MAX_RETRIES=3
```

## Getting an OpenAI API Key

1. Go to https://platform.openai.com/api-keys
2. Sign up or log in
3. Click "Create new secret key"
4. Copy the key (starts with `sk-...`)
5. Add it to your `.env` file

## Model Options

- **gpt-4** (recommended): Best quality, slower, ~$0.03 per 1K tokens
- **gpt-4-turbo**: Good balance of quality and speed
- **gpt-3.5-turbo**: Fastest, cheapest, ~$0.001 per 1K tokens

## Testing Without OpenAI

If you don't have an OpenAI API key, the system will automatically fall back to template-based questions. Just leave `OPENAI_API_KEY` empty or omit it:

```bash
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/orgos
```

The backend will work fine with template questions like:
- "What is the Priority for the task 'Build Feature X'? Options: Critical, High, Medium, Low."

## Example .env File

```bash
# Minimum configuration
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/orgos
OPENAI_API_KEY=sk-proj-abc123...

# Full configuration with all options
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/orgos
OPENAI_API_KEY=sk-proj-abc123...
OPENAI_MODEL=gpt-3.5-turbo
OPENAI_MAX_RETRIES=3
```

## Verifying Configuration

Test your OpenAI setup:

```bash
python -m app.services.llm_questions
```

This will generate 6 sample questions. If it works, you'll see natural language questions. If not, you'll see template-based fallbacks.

