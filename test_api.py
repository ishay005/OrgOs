#!/usr/bin/env python3
"""
Quick API test script to verify the OrgOs backend is working correctly.
Run this after starting the server with: uvicorn app.main:app --reload
"""
import requests
import json
from typing import Optional

BASE_URL = "http://localhost:8000"


def print_response(name: str, response: requests.Response):
    """Pretty print API response"""
    print(f"\n{'='*60}")
    print(f"{name}")
    print(f"{'='*60}")
    print(f"Status: {response.status_code}")
    try:
        print(f"Response: {json.dumps(response.json(), indent=2)}")
    except:
        print(f"Response: {response.text}")


def test_api():
    """Run a complete API test flow"""
    
    print("🚀 Testing OrgOs Backend API")
    print(f"Base URL: {BASE_URL}")
    
    # 1. Health check
    resp = requests.get(f"{BASE_URL}/health")
    print_response("1. Health Check", resp)
    
    # 2. Create users
    alice_data = {
        "name": "Alice",
        "email": "alice@example.com",
        "timezone": "America/New_York",
        "notification_time": "09:00"
    }
    resp = requests.post(f"{BASE_URL}/users", json=alice_data)
    print_response("2. Create User - Alice", resp)
    alice_id = resp.json()["id"]
    
    bob_data = {
        "name": "Bob",
        "email": "bob@example.com",
        "timezone": "America/Los_Angeles"
    }
    resp = requests.post(f"{BASE_URL}/users", json=bob_data)
    print_response("3. Create User - Bob", resp)
    bob_id = resp.json()["id"]
    
    # 3. List users
    resp = requests.get(f"{BASE_URL}/users")
    print_response("4. List All Users", resp)
    
    # 4. Alice aligns with Bob
    resp = requests.post(
        f"{BASE_URL}/alignments",
        headers={"X-User-Id": alice_id},
        json={"target_user_id": bob_id, "align": True}
    )
    print_response("5. Alice Aligns with Bob", resp)
    
    # 5. View alignments
    resp = requests.get(
        f"{BASE_URL}/alignments",
        headers={"X-User-Id": alice_id}
    )
    print_response("6. Alice's Alignments", resp)
    
    # 6. Get task attributes
    resp = requests.get(f"{BASE_URL}/task-attributes")
    print_response("7. Task Attributes (Ontology)", resp)
    
    # 7. Bob creates a task
    task_data = {
        "title": "Implement user authentication",
        "description": "Add OAuth2 authentication to the API"
    }
    resp = requests.post(
        f"{BASE_URL}/tasks",
        headers={"X-User-Id": bob_id},
        json=task_data
    )
    print_response("8. Bob Creates Task", resp)
    task_id = resp.json()["id"]
    
    # 8. Alice views tasks (should see Bob's task since she aligns with him)
    resp = requests.get(
        f"{BASE_URL}/tasks",
        headers={"X-User-Id": alice_id},
        params={"include_self": True, "include_aligned": True}
    )
    print_response("9. Alice Views Tasks (including aligned)", resp)
    
    # 9. Alice gets questions
    resp = requests.get(
        f"{BASE_URL}/questions/next",
        headers={"X-User-Id": alice_id},
        params={"max_questions": 3}
    )
    print_response("10. Alice Gets Questions", resp)
    questions = resp.json()
    
    # 10. Alice answers a question
    if questions:
        question = questions[0]
        answer_data = {
            "question_id": question["question_id"],
            "value": "High",
            "refused": False
        }
        resp = requests.post(
            f"{BASE_URL}/answers",
            headers={"X-User-Id": alice_id},
            json=answer_data
        )
        print_response("11. Alice Answers Question", resp)
    
    # 11. Bob gets questions about his own task
    resp = requests.get(
        f"{BASE_URL}/questions/next",
        headers={"X-User-Id": bob_id},
        params={"max_questions": 3}
    )
    print_response("12. Bob Gets Questions", resp)
    bob_questions = resp.json()
    
    # 12. Bob answers (with different value to create misalignment)
    if bob_questions:
        question = bob_questions[0]
        answer_data = {
            "question_id": question["question_id"],
            "value": "Medium",  # Different from Alice's "High"
            "refused": False
        }
        resp = requests.post(
            f"{BASE_URL}/answers",
            headers={"X-User-Id": bob_id},
            json=answer_data
        )
        print_response("13. Bob Answers Question (differently)", resp)
    
    # 13. Check misalignments
    resp = requests.get(
        f"{BASE_URL}/misalignments",
        headers={"X-User-Id": alice_id}
    )
    print_response("14. Alice Checks Misalignments", resp)
    
    # 14. Test debug endpoint - similarity
    resp = requests.post(
        f"{BASE_URL}/debug/similarity",
        json={
            "attribute_type": "enum",
            "allowed_values": ["Critical", "High", "Medium", "Low"],
            "value_a": "High",
            "value_b": "Medium"
        }
    )
    print_response("15. Debug: Test Similarity", resp)
    
    # 15. Debug: View all attributes
    resp = requests.get(f"{BASE_URL}/debug/attributes")
    print_response("16. Debug: All Attributes", resp)
    
    print("\n" + "="*60)
    print("✅ API Test Complete!")
    print("="*60)
    print(f"\nCreated Users:")
    print(f"  Alice ID: {alice_id}")
    print(f"  Bob ID:   {bob_id}")
    print(f"\nCreated Task:")
    print(f"  Task ID:  {task_id}")
    print(f"\n💡 Tip: View interactive docs at {BASE_URL}/docs")


if __name__ == "__main__":
    try:
        test_api()
    except requests.exceptions.ConnectionError:
        print("\n❌ Error: Could not connect to the API server.")
        print("Make sure the server is running with:")
        print("  uvicorn app.main:app --reload")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()

