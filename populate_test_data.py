#!/usr/bin/env python3
"""
Populate random test data for Bob and Alice
Fills all task attributes from their own perspectives
"""
import requests
import random
from datetime import datetime, timedelta

BASE_URL = "http://localhost:8000"

def populate_test_data():
    print("\n" + "="*70)
    print("🎲 POPULATING TEST DATA")
    print("="*70)
    
    # Get all users
    print("\n1️⃣  Getting users...")
    users = requests.get(f"{BASE_URL}/users").json()
    
    bob = next((u for u in users if "Bob" in u['name']), None)
    alice = next((u for u in users if "Alice" in u['name']), None)
    
    if not bob or not alice:
        print("   ❌ Bob or Alice not found. Creating them...")
        if not bob:
            bob = requests.post(f"{BASE_URL}/users", json={
                "name": "Bob Smith",
                "email": "bob@example.com"
            }).json()
            print(f"   ✅ Created Bob: {bob['id']}")
        if not alice:
            alice = requests.post(f"{BASE_URL}/users", json={
                "name": "Alice Chen",
                "email": "alice@example.com"
            }).json()
            print(f"   ✅ Created Alice: {alice['id']}")
    else:
        print(f"   ✅ Bob: {bob['id']}")
        print(f"   ✅ Alice: {alice['id']}")
    
    # Make them align with each other
    print("\n2️⃣  Setting up alignments...")
    requests.post(
        f"{BASE_URL}/alignments",
        headers={"X-User-Id": alice['id']},
        json={"target_user_id": bob['id'], "align": True}
    )
    requests.post(
        f"{BASE_URL}/alignments",
        headers={"X-User-Id": bob['id']},
        json={"target_user_id": alice['id'], "align": True}
    )
    print("   ✅ Bob and Alice now aligned")
    
    # Get task attributes
    print("\n3️⃣  Getting task attributes...")
    attributes = requests.get(f"{BASE_URL}/task-attributes").json()
    print(f"   ✅ Found {len(attributes)} attributes")
    
    # Attribute value options
    attr_values = {
        "priority": ["Critical", "High", "Medium", "Low"],
        "status": ["Not started", "In progress", "Blocked", "Done"],
        "value_type": ["Customer revenue", "Risk reduction", "Efficiency", "Learning", "Internal hygiene"],
        "is_blocked": ["false", "true"],
        "impact_size": ["1", "2", "3", "4", "5"],
        "direction_confidence": ["1", "2", "3", "4", "5"],
    }
    
    # Create some tasks for each user if they don't have any
    print("\n4️⃣  Creating sample tasks...")
    
    bob_tasks = [
        {"title": "Build Authentication System", "description": "Implement OAuth2 login"},
        {"title": "Setup CI/CD Pipeline", "description": "Automate deployment process"},
        {"title": "Database Migration", "description": "Migrate to PostgreSQL 15"},
    ]
    
    alice_tasks = [
        {"title": "Design New Dashboard", "description": "Create user analytics dashboard"},
        {"title": "Mobile App Redesign", "description": "Update mobile UI/UX"},
        {"title": "API Documentation", "description": "Document all REST endpoints"},
    ]
    
    created_tasks = []
    
    for task_data in bob_tasks:
        task = requests.post(
            f"{BASE_URL}/tasks",
            headers={"X-User-Id": bob['id']},
            json=task_data
        ).json()
        created_tasks.append({"task": task, "owner": bob})
        print(f"   ✅ Bob's task: {task['title']}")
    
    for task_data in alice_tasks:
        task = requests.post(
            f"{BASE_URL}/tasks",
            headers={"X-User-Id": alice['id']},
            json=task_data
        ).json()
        created_tasks.append({"task": task, "owner": alice})
        print(f"   ✅ Alice's task: {task['title']}")
    
    # Get all questions and answer them with random values
    print("\n5️⃣  Filling attribute answers...")
    
    for user in [bob, alice]:
        print(f"\n   Answering for {user['name']}...")
        
        # Get questions
        response = requests.get(
            f"{BASE_URL}/questions/next?max_questions=100",
            headers={"X-User-Id": user['id']}
        )
        
        if response.status_code != 200:
            print(f"   ⚠️  Failed to get questions: {response.status_code}")
            continue
        
        questions = response.json()
        
        if not isinstance(questions, list):
            print(f"   ⚠️  Unexpected response type: {type(questions)}")
            print(f"   Response: {questions}")
            continue
        
        print(f"   Got {len(questions)} questions")
        
        for q in questions:
            if not isinstance(q, dict):
                print(f"   ⚠️  Skipping non-dict question: {q}")
                continue
            # Generate random answer based on attribute type
            attr_name = q.get('attribute_name', '')
            
            if q['attribute_type'] == 'enum':
                if attr_name in attr_values:
                    answer = random.choice(attr_values[attr_name])
                else:
                    answer = random.choice(q.get('allowed_values', ['Unknown']))
            elif q['attribute_type'] == 'bool':
                answer = random.choice(["true", "false"])
            elif q['attribute_type'] == 'int':
                if attr_name in attr_values:
                    answer = random.choice(attr_values[attr_name])
                else:
                    answer = str(random.randint(1, 5))
            elif q['attribute_type'] == 'float':
                answer = str(round(random.uniform(1.0, 5.0), 1))
            else:  # string
                if attr_name == 'main_goal':
                    goals = [
                        "Improve system security and user trust",
                        "Increase development velocity",
                        "Reduce technical debt",
                        "Enhance user experience",
                        "Enable better data analytics"
                    ]
                    answer = random.choice(goals)
                elif attr_name == 'perceived_owner':
                    answer = random.choice([bob['name'], alice['name'], "Team"])
                elif attr_name == 'blocking_reason':
                    answer = random.choice(["Waiting on review", "Dependencies", "None", "Technical blocker"])
                else:
                    answer = "Randomly generated test value"
            
            # Submit answer
            try:
                requests.post(
                    f"{BASE_URL}/answers",
                    headers={"X-User-Id": user['id']},
                    json={
                        "question_id": q['question_id'],
                        "value": answer,
                        "refused": False
                    }
                )
            except Exception as e:
                print(f"      ⚠️  Failed to answer question: {e}")
        
        print(f"   ✅ Answered {len(questions)} questions")
    
    # Summary
    print("\n" + "="*70)
    print("✅ TEST DATA POPULATED!")
    print("="*70)
    print(f"\n✨ Created:")
    print(f"   • {len(bob_tasks)} tasks for Bob")
    print(f"   • {len(alice_tasks)} tasks for Alice")
    print(f"   • Random attribute answers from both perspectives")
    print(f"\n📊 Now both Bob and Alice have answered questions about:")
    print(f"   • Their own tasks")
    print(f"   • Each other's tasks (since they're aligned)")
    print(f"\n🎮 Try the Task Graph now:")
    print(f"   http://localhost:8000/ → Dashboard → Task Graph")
    print(f"\n🔍 Use the filters to explore:")
    print(f"   • Select multiple priorities (e.g., Critical + High)")
    print(f"   • Select multiple statuses (e.g., In progress + Done)")
    print(f"   • Click tasks to see perception differences!")
    print()

if __name__ == "__main__":
    try:
        populate_test_data()
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()

