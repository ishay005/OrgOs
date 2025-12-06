#!/usr/bin/env python3
"""
Test script for similarity engine and misalignment detection.

This script tests the similarity computation for different attribute types
and demonstrates the OpenAI embeddings-based semantic similarity.
"""
import asyncio
from app.services.similarity import compute_similarity, AttributeType


async def test_similarity_engine():
    """Test the similarity engine with various attribute types"""
    
    print("\n" + "="*70)
    print("🔍 Similarity Engine Test")
    print("="*70)
    
    # Test 1: Enum attributes (exact match)
    print("\n📊 Test 1: Enum Attribute (Priority)")
    print("-" * 70)
    
    score1 = await compute_similarity("High", "High", AttributeType.enum)
    print(f"'High' vs 'High': {score1:.3f} (should be 1.0)")
    
    score2 = await compute_similarity("High", "Low", AttributeType.enum)
    print(f"'High' vs 'Low': {score2:.3f} (should be 0.0)")
    
    score3 = await compute_similarity("High", "high", AttributeType.enum)
    print(f"'High' vs 'high': {score3:.3f} (should be 1.0 - case insensitive)")
    
    # Test 2: Boolean attributes
    print("\n📊 Test 2: Boolean Attribute")
    print("-" * 70)
    
    score4 = await compute_similarity("true", "true", AttributeType.bool)
    print(f"'true' vs 'true': {score4:.3f} (should be 1.0)")
    
    score5 = await compute_similarity("true", "false", AttributeType.bool)
    print(f"'true' vs 'false': {score5:.3f} (should be 0.0)")
    
    # Test 3: Integer attributes (distance-based)
    print("\n📊 Test 3: Integer Attribute (Impact Size)")
    print("-" * 70)
    
    score6 = await compute_similarity("5", "5", AttributeType.int)
    print(f"'5' vs '5': {score6:.3f} (should be 1.0)")
    
    score7 = await compute_similarity("5", "4", AttributeType.int)
    print(f"'5' vs '4': {score7:.3f} (diff=1, formula: 1/(1+1)=0.5)")
    
    score8 = await compute_similarity("5", "3", AttributeType.int)
    print(f"'5' vs '3': {score8:.3f} (diff=2, formula: 1/(1+2)=0.33)")
    
    score9 = await compute_similarity("5", "1", AttributeType.int)
    print(f"'5' vs '1': {score9:.3f} (diff=4, formula: 1/(1+4)=0.2)")
    
    # Test 4: Float attributes
    print("\n📊 Test 4: Float Attribute")
    print("-" * 70)
    
    score10 = await compute_similarity("3.5", "3.7", AttributeType.float)
    print(f"'3.5' vs '3.7': {score10:.3f} (diff=0.2)")
    
    score11 = await compute_similarity("2.0", "4.0", AttributeType.float)
    print(f"'2.0' vs '4.0': {score11:.3f} (diff=2.0)")
    
    # Test 5: String attributes with semantic similarity (THIS IS THE KEY FEATURE!)
    print("\n📊 Test 5: String Attribute - Semantic Similarity (OpenAI Embeddings)")
    print("-" * 70)
    print("This uses OpenAI text-embedding-ada-002 for semantic comparison.")
    print()
    
    # Identical strings
    score12 = await compute_similarity(
        "Build user authentication system",
        "Build user authentication system",
        AttributeType.string
    )
    print(f"Identical: {score12:.3f}")
    print(f"  A: 'Build user authentication system'")
    print(f"  B: 'Build user authentication system'")
    print()
    
    # Very similar meaning
    score13 = await compute_similarity(
        "Implement user login and authentication",
        "Build user authentication system",
        AttributeType.string
    )
    print(f"Very similar: {score13:.3f}")
    print(f"  A: 'Implement user login and authentication'")
    print(f"  B: 'Build user authentication system'")
    print()
    
    # Somewhat related
    score14 = await compute_similarity(
        "Add OAuth2 support",
        "Build user authentication system",
        AttributeType.string
    )
    print(f"Somewhat related: {score14:.3f}")
    print(f"  A: 'Add OAuth2 support'")
    print(f"  B: 'Build user authentication system'")
    print()
    
    # Different topics
    score15 = await compute_similarity(
        "Refactor payment processing",
        "Build user authentication system",
        AttributeType.string
    )
    print(f"Different topics: {score15:.3f}")
    print(f"  A: 'Refactor payment processing'")
    print(f"  B: 'Build user authentication system'")
    print()
    
    # Test 6: Main goal examples (realistic use case)
    print("\n📊 Test 6: Main Goal Comparison (Real Use Case)")
    print("-" * 70)
    
    goal_a = "Make the system more secure by adding two-factor authentication"
    goal_b = "Improve security with 2FA implementation"
    score16 = await compute_similarity(goal_a, goal_b, AttributeType.string)
    print(f"Score: {score16:.3f}")
    print(f"  User A: '{goal_a}'")
    print(f"  User B: '{goal_b}'")
    print()
    
    goal_c = "Increase user engagement and retention"
    goal_d = "Make it easier for users to get started"
    score17 = await compute_similarity(goal_c, goal_d, AttributeType.string)
    print(f"Score: {score17:.3f}")
    print(f"  User A: '{goal_c}'")
    print(f"  User B: '{goal_d}'")
    print()
    
    # Test 7: Date attributes
    print("\n📊 Test 7: Date Attribute")
    print("-" * 70)
    
    score18 = await compute_similarity(
        "2025-01-01",
        "2025-01-01",
        AttributeType.date
    )
    print(f"Same date: {score18:.3f}")
    
    score19 = await compute_similarity(
        "2025-01-01",
        "2025-01-02",
        AttributeType.date
    )
    print(f"1 day apart: {score19:.3f} (formula: 1/(1+1)=0.5)")
    
    score20 = await compute_similarity(
        "2025-01-01",
        "2025-01-08",
        AttributeType.date
    )
    print(f"7 days apart: {score20:.3f} (formula: 1/(1+7)=0.125)")
    
    print("\n" + "="*70)
    print("✅ Test complete!")
    print("="*70)
    print("\n💡 Key Insights:")
    print("  - Enum/Bool: Exact match only (1.0 or 0.0)")
    print("  - Int/Float: Distance-based similarity using 1/(1+|a-b|)")
    print("  - String: Semantic similarity using OpenAI embeddings (cosine)")
    print("  - Date: Time-based similarity using 1/(1+days)")
    print("\n📊 Similarity Scale:")
    print("  1.0      = Identical")
    print("  0.8-0.9  = Very similar (minor differences)")
    print("  0.6-0.8  = Somewhat similar (related concepts)")
    print("  0.4-0.6  = Loosely related")
    print("  0.0-0.4  = Different")
    print("\n🎯 Misalignment Threshold: 0.6 (scores below this are reported)")
    print()


async def test_threshold_tuning():
    """
    Demonstrate threshold tuning with examples.
    Shows which scores would be flagged as misalignments.
    """
    print("\n" + "="*70)
    print("⚙️  Threshold Tuning Examples")
    print("="*70)
    print("\nDefault threshold: 0.6 (scores below this are misalignments)")
    print()
    
    test_cases = [
        ("Improve user experience", "Better UX for customers", AttributeType.string, "Similar goals"),
        ("Fix critical bugs", "Add new features", AttributeType.string, "Different goals"),
        ("High", "Medium", AttributeType.enum, "Different priority"),
        ("5", "3", AttributeType.int, "Different impact scores"),
    ]
    
    for value_a, value_b, attr_type, description in test_cases:
        score = await compute_similarity(value_a, value_b, attr_type)
        is_misalignment = score < 0.6
        flag = "🚨 MISALIGNMENT" if is_misalignment else "✅ Aligned"
        
        print(f"{flag} - Score: {score:.3f}")
        print(f"  {description}")
        print(f"  A: '{value_a}'")
        print(f"  B: '{value_b}'")
        print()
    
    print("💡 Adjust threshold in .env with: MISALIGNMENT_THRESHOLD=0.7")
    print()


if __name__ == "__main__":
    print("\n🤖 Similarity Engine & Misalignment Detection Test")
    print("Make sure OPENAI_API_KEY is set in your .env file!")
    print()
    
    asyncio.run(test_similarity_engine())
    asyncio.run(test_threshold_tuning())

