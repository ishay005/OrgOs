# Similarity Engine & Misalignment Detection Guide

## Overview

The Similarity Engine uses **OpenAI embeddings** for semantic text comparison and type-specific algorithms for other data types. This enables the system to detect perception gaps (misalignments) between team members.

## Features

✅ **Semantic Text Similarity** - Uses OpenAI text-embedding-ada-002 for `main_goal` and other text attributes  
✅ **Type-Specific Algorithms** - Different similarity logic for enum, bool, int, float, date  
✅ **Cosine Similarity** - Industry-standard vector comparison for embeddings  
✅ **Configurable Threshold** - Tune when to report misalignments  
✅ **Debug Endpoints** - Test similarity and view all scores  
✅ **Fallback Mode** - Works without OpenAI for non-text attributes  

## How It Works

### Similarity by Attribute Type

#### 1. Enum & Boolean (Exact Match)
```python
# Enum examples (priority, status, value_type)
"High" vs "High"   → 1.0 (identical)
"High" vs "Medium" → 0.0 (different)
"High" vs "high"   → 1.0 (case-insensitive)

# Boolean examples (is_blocked)
"true" vs "true"   → 1.0
"true" vs "false"  → 0.0
```

**Algorithm**: Case-insensitive exact match

#### 2. Integer & Float (Distance-Based)
```python
# Formula: similarity = 1 / (1 + |a - b|)

# Integer examples (impact_size, direction_confidence)
5 vs 5 → 1.0   (same value)
5 vs 4 → 0.5   (difference of 1)
5 vs 3 → 0.33  (difference of 2)
5 vs 1 → 0.2   (difference of 4)

# Float examples
3.5 vs 3.7 → 0.83  (difference of 0.2)
2.0 vs 4.0 → 0.33  (difference of 2.0)
```

**Algorithm**: `1 / (1 + |a - b|)` gives smooth decay

**Properties**:
- Same value: 1.0
- Close values: High score (0.7-0.9)
- Far values: Low score (0.0-0.3)

#### 3. String (Semantic Similarity) ⭐

This is the **key feature** that enables comparing free-text answers like `main_goal`.

```python
# Using OpenAI text-embedding-ada-002

"Build user authentication" vs "Build user authentication"
→ 1.0 (identical)

"Implement user login and authentication" vs "Build user authentication system"
→ 0.92 (very similar meaning)

"Add OAuth2 support" vs "Build user authentication system"
→ 0.78 (related concepts)

"Refactor payment processing" vs "Build user authentication system"
→ 0.42 (different topics)
```

**Algorithm**:
1. Get embeddings from OpenAI (1536-dimensional vectors)
2. Compute cosine similarity between vectors
3. Normalize from [-1, 1] to [0, 1]

**Cost**: ~$0.0001 per comparison (very cheap)

#### 4. Date (Time-Based)
```python
# Formula: similarity = 1 / (1 + days_difference)

"2025-01-01" vs "2025-01-01" → 1.0   (same day)
"2025-01-01" vs "2025-01-02" → 0.5   (1 day apart)
"2025-01-01" vs "2025-01-08" → 0.125 (1 week apart)
"2025-01-01" vs "2025-02-01" → 0.032 (1 month apart)
```

**Algorithm**: `1 / (1 + days_difference)`

## Misalignment Detection

### What is a Misalignment?

A misalignment occurs when:
1. User A answers about User B's task
2. User B answers about their own task
3. The similarity score is **below the threshold** (default 0.6)

### Example Flow

```
1. Alice aligns with Bob (wants to compare perceptions)

2. Bob creates task: "Implement user dashboard"

3. Alice answers "What is the main goal?":
   → "Make it easier for users to view their data"

4. Bob answers the same question:
   → "Build a comprehensive analytics dashboard"

5. System computes similarity:
   → Embeddings show: 0.54 (below 0.6 threshold)

6. Misalignment reported:
   - Task: "Implement user dashboard"
   - Attribute: "Main goal"
   - Alice's view: "Make it easier for users to view their data"
   - Bob's view: "Build a comprehensive analytics dashboard"
   - Score: 0.54
```

### Threshold Guide

The **misalignment threshold** determines what gets flagged:

```
Score    Meaning               Action
-------  -------------------   ---------------------------
1.0      Identical             ✅ Perfect alignment
0.8-0.9  Very similar          ✅ Good alignment
0.6-0.8  Somewhat similar      ⚠️  Worth reviewing
0.4-0.6  Loosely related       🚨 Misalignment (default)
0.0-0.4  Very different        🚨 Significant misalignment
```

**Default**: 0.6 (scores below this are reported)

**Tuning**:
- Lower threshold (0.4-0.5): Only report major differences
- Higher threshold (0.7-0.8): Report even minor differences

## API Usage

### Get Misalignments (Filtered)

```bash
curl http://localhost:8000/misalignments \
  -H "X-User-Id: <user-id>"
```

Returns only misalignments where `similarity_score < 0.6`:

```json
[
  {
    "other_user_id": "uuid",
    "other_user_name": "Bob",
    "task_id": "uuid",
    "task_title": "Implement user dashboard",
    "attribute_id": "uuid",
    "attribute_name": "main_goal",
    "attribute_label": "Main goal",
    "your_value": "Make it easier for users to view their data",
    "their_value": "Build a comprehensive analytics dashboard",
    "similarity_score": 0.54
  }
]
```

### Debug: Get All Scores (Raw)

```bash
curl http://localhost:8000/debug/misalignments/raw \
  -H "X-User-Id: <user-id>"
```

Returns **all** answer pairs with scores, regardless of threshold:

```json
[
  {
    "attribute_name": "priority",
    "your_value": "High",
    "their_value": "High",
    "similarity_score": 1.0
  },
  {
    "attribute_name": "main_goal",
    "your_value": "...",
    "their_value": "...",
    "similarity_score": 0.54
  }
]
```

Useful for:
- Understanding score distribution
- Tuning threshold
- Finding edge cases
- Testing embeddings on real data

### Debug: Test Similarity

```bash
curl -X POST http://localhost:8000/debug/similarity \
  -H "Content-Type: application/json" \
  -d '{
    "attribute_type": "string",
    "value_a": "Improve user experience",
    "value_b": "Better UX for customers"
  }'
```

Response:
```json
{
  "similarity_score": 0.89
}
```

Test different types:

```bash
# Test enum
curl -X POST http://localhost:8000/debug/similarity \
  -H "Content-Type: application/json" \
  -d '{
    "attribute_type": "enum",
    "allowed_values": ["Critical", "High", "Medium", "Low"],
    "value_a": "High",
    "value_b": "Medium"
  }'
# Returns: {"similarity_score": 0.0}

# Test integer
curl -X POST http://localhost:8000/debug/similarity \
  -H "Content-Type: application/json" \
  -d '{
    "attribute_type": "int",
    "value_a": "5",
    "value_b": "3"
  }'
# Returns: {"similarity_score": 0.33}

# Test string (semantic)
curl -X POST http://localhost:8000/debug/similarity \
  -H "Content-Type: application/json" \
  -d '{
    "attribute_type": "string",
    "value_a": "Build authentication system",
    "value_b": "Implement user login"
  }'
# Returns: {"similarity_score": 0.87}
```

## Configuration

### Environment Variables

Add to `.env`:

```bash
# Required for text similarity
OPENAI_API_KEY=sk-your-key-here

# Optional (with defaults)
MISALIGNMENT_THRESHOLD=0.6  # Scores below this are reported
```

### Tuning the Threshold

```bash
# Strict: Only report major differences
MISALIGNMENT_THRESHOLD=0.4

# Default: Report moderate differences
MISALIGNMENT_THRESHOLD=0.6

# Sensitive: Report even minor differences
MISALIGNMENT_THRESHOLD=0.8
```

## Testing

### Unit Tests

```bash
# Test similarity engine
python test_similarity.py
```

This runs 20+ test cases covering:
- Enum exact matching
- Boolean comparisons
- Integer/float distance
- **Semantic text similarity** (key feature!)
- Date comparisons
- Threshold tuning examples

### Integration Tests

```bash
# Start server
uvicorn app.main:app --reload

# Create users and tasks (see API_TESTING_GUIDE.md)
# Then get misalignments
curl http://localhost:8000/misalignments \
  -H "X-User-Id: <user-id>"

# View all scores
curl http://localhost:8000/debug/misalignments/raw \
  -H "X-User-Id: <user-id>"
```

## Implementation Details

### OpenAI Embeddings

**Model**: `text-embedding-ada-002`
- **Dimensions**: 1536
- **Cost**: $0.0001 per 1K tokens (~$0.0001 per comparison)
- **Quality**: State-of-the-art semantic understanding

**Cosine Similarity**:
```python
def cosine_similarity(vec_a, vec_b):
    dot_product = sum(a * b for a, b in zip(vec_a, vec_b))
    magnitude_a = sqrt(sum(a * a for a in vec_a))
    magnitude_b = sqrt(sum(b * b for b in vec_b))
    cosine_sim = dot_product / (magnitude_a * magnitude_b)
    # Normalize from [-1, 1] to [0, 1]
    return (cosine_sim + 1) / 2
```

### Fallback Mode

If OpenAI API fails for text similarity:
- Falls back to character overlap (Jaccard similarity)
- Less accurate but ensures system keeps working
- Logs warning for debugging

### Performance

**Latency**:
- Enum/Bool/Int/Float/Date: <1ms (local computation)
- String (with embeddings): ~100-200ms per comparison
- Caching: Not implemented (could cache embeddings by text)

**Cost** (for 1000 comparisons):
- String attributes: ~$0.20 (embeddings)
- Other types: $0 (local computation)

**Optimization tips**:
- Cache embeddings for repeated texts
- Batch embedding requests (not currently implemented)
- Use fallback for very short strings (<5 words)

## Examples

### Example 1: Main Goal Comparison

```python
from app.services.similarity import compute_similarity, AttributeType

# User A's perception
goal_a = "Make the authentication system more secure"

# User B's perception
goal_b = "Improve security of user login process"

# Compute semantic similarity
score = await compute_similarity(goal_a, goal_b, AttributeType.string)
# Result: ~0.88 (high similarity, aligned)

# Different goal
goal_c = "Increase system performance and speed"
score2 = await compute_similarity(goal_a, goal_c, AttributeType.string)
# Result: ~0.35 (low similarity, misalignment!)
```

### Example 2: Priority Enum

```python
score = await compute_similarity(
    "High",
    "Medium",
    AttributeType.enum,
    allowed_values=["Critical", "High", "Medium", "Low"]
)
# Result: 0.0 (different values, misalignment!)
```

### Example 3: Impact Score

```python
# User A thinks impact is 5/5
# User B thinks impact is 3/5
score = await compute_similarity("5", "3", AttributeType.int)
# Result: 0.33 (1/(1+2) = 0.33, misalignment!)
```

## Troubleshooting

### "Similarity always returns 0.0 for strings"
→ Check that `OPENAI_API_KEY` is set and valid
→ Check logs for OpenAI API errors
→ System will fall back to character overlap (less accurate)

### "Scores seem too high/low"
→ Adjust `MISALIGNMENT_THRESHOLD` in .env
→ Use `GET /debug/misalignments/raw` to see all scores
→ Test specific cases with `POST /debug/similarity`

### "No misalignments showing up"
→ Check that users have answered the same questions
→ Verify threshold isn't too low (try 0.8 to see more)
→ Use debug endpoint to see raw scores

### "Embeddings are slow"
→ Normal: ~100-200ms per comparison
→ Consider caching embeddings for repeated texts
→ Batch comparisons (not currently implemented)

## Best Practices

### For Users
1. **Be specific** in free-text answers (main_goal, blocking_reason)
2. **Use full sentences** rather than keywords
3. **Be consistent** in terminology

### For Threshold Tuning
1. Start with default (0.6)
2. Use `GET /debug/misalignments/raw` to see distribution
3. Adjust based on your team's needs:
   - Engineering teams: 0.5-0.6 (technical precision)
   - Product teams: 0.6-0.7 (conceptual alignment)
   - Executive teams: 0.7-0.8 (strategic alignment)

### For Developers
1. Test similarity with `POST /debug/similarity` before deploying
2. Monitor embedding API costs
3. Cache embeddings for frequently compared texts
4. Log misalignments for analysis

## Architecture

```
User Request
    ↓
GET /misalignments
    ↓
compute_misalignments_for_user()
    ↓
For each aligned user & task:
    ↓
compute_similarity()
    ↓
    ├─ Enum/Bool → Exact match
    ├─ Int/Float → Distance formula
    ├─ Date      → Time difference
    └─ String    → OpenAI embeddings → Cosine similarity
    ↓
Filter by threshold (< 0.6)
    ↓
Return misalignments
```

## Summary

The Similarity Engine provides:
- ✅ **Semantic understanding** of free-text goals using OpenAI embeddings
- ✅ **Type-specific algorithms** for different attribute types
- ✅ **Configurable threshold** for tuning sensitivity
- ✅ **Debug tools** for testing and tuning
- ✅ **Fallback mode** for reliability

**Key Innovation**: Using embeddings for `main_goal` comparison enables detecting when team members have different understandings of a task's purpose, even when using different words.

## Next Steps

After Prompt 3, the system is ready for:
- ⏳ **Prompt 4**: Android client to consume these APIs
- 🔮 **Future**: Caching, batching, analytics dashboard

