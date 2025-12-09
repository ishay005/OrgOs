# Robin Pending Questions System

## Overview

Robin now operates with a **strict pending questions system** that controls when and what questions can be asked. The system ensures Robin only asks questions when there are relevant pending items, making interactions more focused and purposeful.

---

## Key Components

### 1. Pending Questions Service (`app/services/questions.py`)

**What it does:**
- Tracks what questions need to be asked to each user
- Identifies missing, stale, or misaligned attributes
- Assigns priority to each pending question
- Returns a sorted list of pending items

**PendingQuestion Model:**
```python
class PendingQuestion(BaseModel):
    id: str                    # Composite ID
    target_user_id: UUID       # Who the question is about
    task_id: UUID | None       # Related task (or None for user-level)
    attribute_name: str        # e.g., "priority", "status"
    attribute_label: str       # Human-readable label
    reason: str                # "missing" | "stale" | "misaligned"
    priority: int              # Lower = more important
```

**Logic:**
- **Missing**: No answer exists for this (task, attribute) pair
- **Stale**: Answer is older than 7 days
- **Misaligned**: Similarity score < 0.6 with someone else's answer

**Priority Calculation:**
- Base: 100
- Missing: -30
- Misaligned: -20
- Stale: -10
- Important attributes (priority, status, main_goal): -15

---

### 2. Three Operating Modes

Robin operates in exactly **3 modes**, each with specific behavior:

#### Mode 1: Morning Brief (`morning_brief`)
**Triggered by:** User typing "morning_brief", "brief", or "morning brief"

**Behavior:**
- **If `has_relevant_pending == False`:**
  - Give short overview of top tasks (what's done, in progress, blocked)
  - **DO NOT ask any questions**
  - Be concise (1-3 bullet points)

- **If `has_relevant_pending == True`:**
  - Give short overview of top tasks
  - **May ask up to 2 questions** about the top tasks
  - Questions must be about items in the pending list
  - Questions appear at the end of the brief

**Context includes:**
- User name, manager, employees
- User's tasks + aligned users' tasks
- Up to 2 relevant pending items (filtered to top tasks)

---

#### Mode 2: User Question (`user_question`)
**Triggered by:** Any message that is not a special trigger (default mode)

**Behavior:**
- **If `has_relevant_pending == False`:**
  - Answer the user's question directly
  - **DO NOT ask any follow-up questions**
  - Say "I don't know" if information is missing

- **If `has_relevant_pending == True`:**
  - Answer the user's question first
  - **May ask 1 follow-up question** if it's directly related to:
    - The user's original question, AND
    - One of the pending items
  - If no pending item fits naturally, skip the follow-up

**Context includes:**
- User name, manager, employees
- User's tasks + aligned users' tasks
- Up to 1 relevant pending item (filtered by topic, simplified)

---

#### Mode 3: Collect Data (`collect_data`)
**Triggered by:** User typing "collect_data", "collect", "update", or "fill attributes"

**Behavior:**
- **If `has_relevant_pending == False`:**
  - Say briefly that everything looks up to date
  - **DO NOT ask any questions**

- **If `has_relevant_pending == True`:**
  - Ask questions to fill missing/stale/misaligned attributes
  - Group related attributes for the same task when possible
  - **Ask up to 3 questions** in this turn
  - Stay strictly within pending items

**Context includes:**
- User name
- **Only** tasks and users related to the pending items (simplified context)
- Up to 5 high-priority pending items

---

## System Prompts

Each mode has **2 prompts** (with/without pending questions), making **6 total prompts**.

All prompts are:
- **Short and clear** (100-150 words)
- **Strict about question limits**
- **Specify JSON output format**

Example (Morning Brief with Pending):
```
Mode: Morning brief with pending questions.

Your goals:
- Give this user a very short overview of today's situation over their top tasks: 
  what's done, what's in progress, what's blocked, and what deserves attention next.
- You may ask at most two focused follow-up questions, but only about the tasks 
  and attributes listed in the pending items.

Rules:
- Start with the brief (1–3 short bullet points or short paragraphs).
- Only then, if it clearly fits, embed at most two questions at the end.
- Do not ask about anything that is not in the pending list.

Output format - you MUST respond with valid JSON:
{
  "display_messages": ["brief text", "optional question 1", "optional question 2"],
  "updates": []
}
```

---

## How It Works (Flow)

### User sends message: "morning_brief"

1. **Classify mode**: `morning_brief`
2. **Get pending questions**: Call `_get_pending_sync()` → returns 15 pending items
3. **Build context**:
   - Get user snapshot (name, manager, employees)
   - Get task snapshot (15 tasks with attributes)
4. **Filter pending by mode**:
   - Mode is `morning_brief` → filter to tasks in top 5 tasks
   - Limit to 2 items
   - Result: 2 relevant pending items
5. **Set flag**: `has_relevant_pending = True`
6. **Build prompt**:
   - System prompt: "Morning brief with pending questions" version
   - Context: user, manager, employees, 15 tasks, 2 pending items
7. **Call OpenAI**: GPT-5 mini with the prompt
8. **Parse response**: Extract `display_messages` and `updates`
9. **Return**: RobinReply with messages and updates

---

### User sends message: "Hello Robin"

1. **Classify mode**: `user_question` (default)
2. **Get pending questions**: 15 pending items
3. **Build context**: User snapshot + task snapshot
4. **Filter pending by mode**:
   - Mode is `user_question` → limit to 1 high-priority item
   - Result: 1 relevant pending item
5. **Set flag**: `has_relevant_pending = True`
6. **Build prompt**:
   - System prompt: "Answer user question with a related follow-up" version
   - Context: user info, tasks, 1 pending item
7. **Call OpenAI**
8. **Parse and return**

---

### User sends message: "collect_data"

1. **Classify mode**: `collect_data`
2. **Get pending questions**: 15 pending items
3. **Build context**: User snapshot (name only) + pending items
4. **Filter pending by mode**:
   - Mode is `collect_data` → return top 5 items
   - Result: 5 relevant pending items
5. **Set flag**: `has_relevant_pending = True`
6. **Build prompt**:
   - System prompt: "Collect perception data for pending items" version
   - **Simplified context**: Just user name + pending items summary
7. **Call OpenAI**
8. **Parse and return**

---

## Critical Rules

### ✅ Robin MUST:
1. Only ask questions when `has_relevant_pending == True`
2. Stay within the question limits per mode:
   - Morning brief: max 2 questions
   - User question: max 1 question
   - Collect data: max 3 questions
3. Only ask about items in the `pending_relevant` list
4. Always output valid JSON with `display_messages` and `updates`

### ❌ Robin MUST NOT:
1. "Sneak in" questions when `has_relevant_pending == False`
2. Ask about attributes/tasks not in the pending list
3. Exceed the question limits for each mode
4. Ask unrelated questions in `user_question` mode

---

## Context per Mode (Summary)

| Mode | Context Includes |
|------|-----------------|
| `morning_brief` (both) | User name, manager, employees, user tasks, aligned tasks, pending (filtered) |
| `user_question` (both) | User name, manager, employees, user tasks, aligned tasks, pending (filtered) |
| `collect_data` (pending) | User name, pending items only (simplified) |
| `collect_data` (no pending) | User name only |

---

## Debug Feature: View Last Prompt

**What it does:**
- Stores the full prompt sent to OpenAI in `lastRobinPrompt`
- Button: "🐛 View Last Prompt" in the chat header
- Opens a modal with the full JSON of:
  - Model name
  - Mode
  - `has_relevant_pending` flag
  - Pending count
  - Full messages array sent to OpenAI

**How to use:**
1. Send a message to Robin
2. Click "🐛 View Last Prompt" button
3. View the full prompt in the modal
4. Use this to understand exactly what Robin sees

---

## Benefits

1. **Predictable behavior**: Robin's behavior is now deterministic based on mode
2. **No "sneaky" questions**: Robin only asks when there are relevant pending items
3. **Focused interactions**: Each mode has a clear purpose
4. **Simplified context**: Context is tailored to the mode's needs
5. **Testable**: Each mode can be tested independently
6. **Debuggable**: View exactly what prompt was sent to OpenAI

---

## Testing the System

### Test 1: Morning Brief with No Pending Items
1. Ensure all your task attributes are filled
2. Type: `morning_brief`
3. **Expected**: Robin gives a brief overview, **NO questions asked**

### Test 2: Morning Brief with Pending Items
1. Leave some task attributes empty (e.g., status, priority)
2. Type: `morning_brief`
3. **Expected**: Robin gives a brief, then asks **up to 2 questions** about the top tasks

### Test 3: User Question with No Pending Items
1. Ensure all attributes are filled
2. Ask: "What tasks do I have?"
3. **Expected**: Robin answers, **NO follow-up questions**

### Test 4: User Question with Pending Items
1. Leave some attributes empty
2. Ask: "What tasks do I have?"
3. **Expected**: Robin answers, then **may ask 1 related follow-up** if it fits

### Test 5: Collect Data with Pending Items
1. Leave many attributes empty
2. Type: `collect_data`
3. **Expected**: Robin asks **up to 3 questions** to fill the gaps

### Test 6: Collect Data with No Pending Items
1. Ensure all attributes are filled
2. Type: `collect_data`
3. **Expected**: Robin says "Everything looks up to date", **NO questions**

### Test 7: View Debug Prompt
1. Send any message to Robin
2. Click "🐛 View Last Prompt"
3. **Expected**: Modal shows the full prompt with mode, pending count, and messages

---

## Technical Implementation Details

### Files Changed
1. **`app/services/questions.py`** (NEW)
   - `PendingQuestion` model
   - `get_pending_questions_for_user()` function
   - Priority calculation logic

2. **`app/services/robin_orchestrator.py`** (REWRITTEN)
   - Mode classification
   - Pending question filtering by mode
   - Mode-specific context building
   - Mode-specific system prompts
   - Sync wrapper for pending questions

3. **Frontend (Already Implemented)**
   - `static/app.js`: Debug prompt capture and display
   - `static/index.html`: "🐛 View Last Prompt" button and modal

### Database Tables Used
- `users` - User info
- `tasks` - Task info
- `attribute_definitions` - Available attributes
- `attribute_answers` - User's answers
- `alignment_edges` - Who aligns with whom
- `similarity_scores` - Misalignment detection

---

## Current Behavior

When you send a message to Robin:
1. **No special trigger** → `user_question` mode
2. **"morning_brief"** → `morning_brief` mode
3. **"collect_data"** → `collect_data` mode

The system automatically:
- Detects pending questions
- Filters them by relevance to the mode
- Builds appropriate context
- Uses the right prompt
- Enforces question limits

---

## Next Steps

1. **Test all 3 modes** to verify behavior
2. **Use debug prompt viewer** to understand what Robin sees
3. **Fill some attributes** to see how pending list changes
4. **Try different scenarios** (all filled, partially filled, empty)

The system is now live and running on your local server!

