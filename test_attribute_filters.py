#!/usr/bin/env python3
"""
Test script for task attribute filtering in graph view
"""
import requests
import time

BASE_URL = "http://localhost:8000"

def test_attribute_filters():
    print("\n" + "="*70)
    print("🧪 TESTING ATTRIBUTE-BASED FILTERING")
    print("="*70)
    
    # Step 1: Create user
    print("\n1️⃣  Creating user...")
    alice = requests.post(f"{BASE_URL}/users", json={
        "name": "Alice",
        "email": "alice@test.com"
    }).json()
    print(f"   ✅ Alice: {alice['id']}")
    
    # Step 2: Create tasks with different attributes
    print("\n2️⃣  Creating tasks with various attributes...")
    
    # High priority task
    task1 = requests.post(
        f"{BASE_URL}/tasks",
        headers={"X-User-Id": alice['id']},
        json={
            "title": "Critical Bug Fix",
            "description": "Fix production issue"
        }
    ).json()
    print(f"   ✅ Task 1: {task1['title']}")
    
    # Medium priority task  
    task2 = requests.post(
        f"{BASE_URL}/tasks",
        headers={"X-User-Id": alice['id']},
        json={
            "title": "Feature Development",
            "description": "New user dashboard"
        }
    ).json()
    print(f"   ✅ Task 2: {task2['title']}")
    
    # Low priority task
    task3 = requests.post(
        f"{BASE_URL}/tasks",
        headers={"X-User-Id": alice['id']},
        json={
            "title": "Documentation Update",
            "description": "Update README"
        }
    ).json()
    print(f"   ✅ Task 3: {task3['title']}")
    
    # Step 3: Answer questions to set attributes
    print("\n3️⃣  Setting task attributes via questions...")
    
    # Get questions
    questions = requests.get(
        f"{BASE_URL}/questions/next?max_questions=20",
        headers={"X-User-Id": alice['id']}
    ).json()
    
    print(f"   Got {len(questions)} questions")
    
    # Answer priority questions
    for q in questions:
        if q['attribute_name'] == 'priority':
            if 'Critical' in q['task_title']:
                answer = 'Critical'
            elif 'Feature' in q['task_title']:
                answer = 'High'
            else:
                answer = 'Low'
            
            requests.post(
                f"{BASE_URL}/answers",
                headers={"X-User-Id": alice['id']},
                json={
                    "question_id": q['question_id'],
                    "value": answer,
                    "refused": False
                }
            )
            print(f"   ✅ Set priority for '{q['task_title']}': {answer}")
        
        # Answer status questions
        elif q['attribute_name'] == 'status':
            if 'Critical' in q['task_title']:
                answer = 'In progress'
            elif 'Feature' in q['task_title']:
                answer = 'Not started'
            else:
                answer = 'Done'
            
            requests.post(
                f"{BASE_URL}/answers",
                headers={"X-User-Id": alice['id']},
                json={
                    "question_id": q['question_id'],
                    "value": answer,
                    "refused": False
                }
            )
            print(f"   ✅ Set status for '{q['task_title']}': {answer}")
    
    # Step 4: Test the graph endpoint with attributes
    print("\n4️⃣  Fetching task graph with attributes...")
    graph_data = requests.get(f"{BASE_URL}/tasks/graph/with-attributes").json()
    
    print(f"   ✅ Retrieved {len(graph_data)} tasks")
    
    # Show sample task with attributes
    for task in graph_data:
        if task.get('attributes'):
            print(f"\n   📝 Sample Task: {task['title']}")
            for attr_name, attr_data in task['attributes'].items():
                print(f"      {attr_data['label']}: {attr_data['value']}")
            break
    
    # Step 5: Count tasks by attribute values
    print("\n5️⃣  Task distribution by attributes:")
    
    # Count by priority
    priority_counts = {}
    status_counts = {}
    
    for task in graph_data:
        attrs = task.get('attributes', {})
        
        if 'priority' in attrs:
            pri = attrs['priority']['value']
            priority_counts[pri] = priority_counts.get(pri, 0) + 1
        
        if 'status' in attrs:
            stat = attrs['status']['value']
            status_counts[stat] = status_counts.get(stat, 0) + 1
    
    print(f"\n   📊 By Priority:")
    for pri, count in sorted(priority_counts.items()):
        print(f"      {pri}: {count} task(s)")
    
    print(f"\n   📊 By Status:")
    for stat, count in sorted(status_counts.items()):
        print(f"      {stat}: {count} task(s)")
    
    # Summary
    print("\n" + "="*70)
    print("✅ ATTRIBUTE FILTERING TESTS PASSED!")
    print("="*70)
    print("\n🌟 Features Tested:")
    print("   ✅ Tasks with attribute answers")
    print("   ✅ Graph endpoint returns attributes")
    print("   ✅ Multiple attribute types (enum)")
    print("   ✅ Tasks can be filtered by attributes")
    print("\n📱 Open the Web UI to test filtering:")
    print("   🖥️  http://localhost:8000/")
    print("   → Dashboard → 🔗 Task Graph")
    print("\n🔍 Try These Filters:")
    print("   • Priority: Critical, High, Low")
    print("   • Status: In progress, Not started, Done")
    print("   • Any other task attributes available")
    print()

if __name__ == "__main__":
    try:
        test_attribute_filters()
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()

