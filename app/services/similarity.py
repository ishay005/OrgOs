"""
Similarity computation module using OpenAI embeddings for semantic comparison.

This module computes similarity scores between attribute values based on their type:
- Enum/Bool: Exact match (1.0 or 0.0)
- Int/Float: Distance-based similarity
- String: Semantic similarity using OpenAI embeddings
- Date: Time-based similarity
"""
import logging
import math
from enum import Enum
from datetime import datetime, date
from typing import Optional
from openai import AsyncOpenAI, OpenAIError

from app.config import settings

logger = logging.getLogger(__name__)


class AttributeType(str, Enum):
    """Attribute types for similarity computation"""
    string = "string"
    enum = "enum"
    int = "int"
    float = "float"
    bool = "bool"
    date = "date"


# Initialize OpenAI client for embeddings
def get_openai_client() -> AsyncOpenAI:
    """Get configured OpenAI client for embeddings"""
    if not settings.openai_api_key:
        logger.warning("OpenAI API key not configured, embeddings will fail")
    return AsyncOpenAI(api_key=settings.openai_api_key)


async def _get_embedding(text: str, client: Optional[AsyncOpenAI] = None) -> list[float]:
    """
    Get OpenAI embedding for a text string.
    
    Args:
        text: Text to embed
        client: Optional OpenAI client (creates new one if not provided)
    
    Returns:
        Embedding vector (1536 dimensions for text-embedding-ada-002)
    
    Raises:
        OpenAIError: If embedding fails
    """
    if client is None:
        client = get_openai_client()
    
    try:
        response = await client.embeddings.create(
            model="text-embedding-ada-002",
            input=text
        )
        return response.data[0].embedding
    except OpenAIError as e:
        logger.error(f"Failed to get embedding for text: {e}")
        raise


def _cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:
    """
    Compute cosine similarity between two vectors.
    
    Args:
        vec_a: First embedding vector
        vec_b: Second embedding vector
    
    Returns:
        Cosine similarity in [0, 1] (normalized from [-1, 1])
    """
    # Compute dot product
    dot_product = sum(a * b for a, b in zip(vec_a, vec_b))
    
    # Compute magnitudes
    magnitude_a = math.sqrt(sum(a * a for a in vec_a))
    magnitude_b = math.sqrt(sum(b * b for b in vec_b))
    
    # Avoid division by zero
    if magnitude_a == 0 or magnitude_b == 0:
        return 0.0
    
    # Cosine similarity is in [-1, 1], normalize to [0, 1]
    cosine_sim = dot_product / (magnitude_a * magnitude_b)
    normalized = (cosine_sim + 1) / 2
    
    return max(0.0, min(1.0, normalized))


async def compute_similarity(
    value_a: str,
    value_b: str,
    attribute_type: AttributeType,
    allowed_values: Optional[list[str]] = None
) -> float:
    """
    Compute similarity between two attribute values.
    
    Args:
        value_a: First value (as string)
        value_b: Second value (as string)
        attribute_type: Type of the attribute
        allowed_values: Allowed values for enum types (optional)
    
    Returns:
        Similarity score in [0.0, 1.0] where:
        - 1.0 = identical/perfect match
        - 0.0 = completely different
    
    Behavior by type:
    - enum/bool: Exact match → 1.0, else 0.0
    - int/float: Distance-based similarity using 1/(1+|a-b|)
    - string: Semantic similarity using OpenAI embeddings (cosine similarity)
    - date: Time-based similarity (closer dates = higher score)
    
    Example:
        >>> await compute_similarity("High", "High", AttributeType.enum)
        1.0
        >>> await compute_similarity("High", "Low", AttributeType.enum)
        0.0
        >>> await compute_similarity("Build auth", "Add authentication", AttributeType.string)
        0.85  # High semantic similarity
    """
    # Handle None/empty values
    if not value_a or not value_b:
        return 0.0
    
    # Normalize whitespace
    value_a = value_a.strip()
    value_b = value_b.strip()
    
    # Exact match always returns 1.0
    if value_a.lower() == value_b.lower():
        return 1.0
    
    # Type-specific similarity computation
    if attribute_type == AttributeType.enum or attribute_type == AttributeType.bool:
        # Enum and bool: exact match only
        # Case-insensitive comparison
        return 1.0 if value_a.lower() == value_b.lower() else 0.0
    
    elif attribute_type == AttributeType.int or attribute_type == AttributeType.float:
        # Numeric: distance-based similarity
        # Formula: similarity = 1 / (1 + |a - b|)
        # This gives:
        #   - same value: 1.0
        #   - difference of 1: 0.5
        #   - difference of 4: 0.2
        #   - difference of 9: 0.1
        try:
            num_a = float(value_a)
            num_b = float(value_b)
            distance = abs(num_a - num_b)
            similarity = 1.0 / (1.0 + distance)
            return similarity
        except ValueError:
            logger.warning(f"Failed to parse numeric values: '{value_a}', '{value_b}'")
            return 0.0
    
    elif attribute_type == AttributeType.string:
        # String: semantic similarity using OpenAI embeddings
        # This is the key feature for comparing free-text like "main_goal"
        try:
            client = get_openai_client()
            
            # Get embeddings for both texts
            embedding_a = await _get_embedding(value_a, client)
            embedding_b = await _get_embedding(value_b, client)
            
            # Compute cosine similarity
            similarity = _cosine_similarity(embedding_a, embedding_b)
            
            logger.info(
                f"String similarity: '{value_a[:50]}...' vs '{value_b[:50]}...' = {similarity:.3f}"
            )
            
            return similarity
            
        except OpenAIError as e:
            logger.error(f"Failed to compute embedding similarity, using fallback: {e}")
            # Fallback: simple character overlap
            return _fallback_string_similarity(value_a, value_b)
    
    elif attribute_type == AttributeType.date:
        # Date: time-based similarity
        # Closer dates have higher similarity
        # Formula: similarity = 1 / (1 + days_difference)
        try:
            # Try parsing as ISO date strings
            date_a = datetime.fromisoformat(value_a.replace('Z', '+00:00'))
            date_b = datetime.fromisoformat(value_b.replace('Z', '+00:00'))
            
            # Calculate difference in days
            diff_days = abs((date_a - date_b).days)
            
            # Similarity decreases with time difference
            # Same day: 1.0, 1 day apart: 0.5, 7 days: 0.125, 30 days: 0.032
            similarity = 1.0 / (1.0 + diff_days)
            
            return similarity
            
        except (ValueError, TypeError) as e:
            logger.warning(f"Failed to parse dates: '{value_a}', '{value_b}': {e}")
            # Fallback: string comparison
            return 1.0 if value_a == value_b else 0.0
    
    else:
        # Unknown type: default to string comparison
        logger.warning(f"Unknown attribute type: {attribute_type}")
        return 1.0 if value_a == value_b else 0.0


def _fallback_string_similarity(value_a: str, value_b: str) -> float:
    """
    Fallback string similarity when embeddings fail.
    Uses simple character overlap ratio (Jaccard similarity).
    
    This is much less accurate than embeddings but works without OpenAI.
    """
    set_a = set(value_a.lower())
    set_b = set(value_b.lower())
    
    if not set_a or not set_b:
        return 0.0
    
    intersection = len(set_a & set_b)
    union = len(set_a | set_b)
    
    return intersection / union if union > 0 else 0.0

