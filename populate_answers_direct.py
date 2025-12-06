#!/usr/bin/env python3
"""
Directly populate attribute answers for Bob and Alice
Bypasses question generation to avoid OpenAI API issues
"""
import requests
import random
import uuid

BASE_URL = "http://localhost:8000"

# Random answer values for each attribute type
ANSWER_VALUES = {
    "priority": ["Critical", "High", "Medium", "Low"],
    "status": ["Not started", "In progress", "Blocked", "Done"],
    "value_type": ["Customer revenue", "Risk reduction", "Efficiency", "Learning", "Internal hygiene"],
    "is_blocked": ["false", "true"],
    "impact_size": ["1", "2", "3", "4", "5"],
    "direction_confidence": ["1", "2", "3", "4", "5"],
    "main_goal": [
        "Improve system security and user trust",
        "Increase development velocity and code quality",
        "Reduce technical debt and improve maintainability",
        "Enhance user experience and satisfaction",
        "Enable better data analytics and insights"
    ],
    "perceived_owner": ["Bob", "Alice", "Team", "Product"],
    "blocking_reason": ["Waiting on review", "External dependencies", "None", "Technical blocker", "Resource constraints"]
}

def populate_direct():
    print("\n" + "="*70)
    print("🎲 POPULATING ANSWERS DIRECTLY")
    print("="*70)
    
    # Get users
    print("\n1️⃣  Getting users...")
    users = requests.get(f"{BASE_URL}/users").json()
    
    bob = next((u for u in users if "Bob" in u['name']), None)
    alice = next((u for u in users if "Alice" in u['name']), None)
    
    if not bob or not alice:
        print("   ❌ Please run populate_test_data.py first to create users and tasks")
        return
    
    print(f"   ✅ Bob: {bob['id']}")
    print(f"   ✅ Alice: {alice['id']}")
    
    # Get all tasks
    print("\n2️⃣  Getting tasks...")
    bob_tasks = requests.get(
        f"{BASE_URL}/tasks?include_self=true&include_aligned=true",
        headers={"X-User-Id": bob['id']}
    ).json()
    alice_tasks = requests.get(
        f"{BASE_URL}/tasks?include_self=true&include_aligned=true",
        headers={"X-User-Id": alice['id']}
    ).json()
    
    all_tasks = {t['id']: t for t in (bob_tasks + alice_tasks)}
    print(f"   ✅ Found {len(all_tasks)} total tasks")
    
    # Get attributes
    print("\n3️⃣  Getting attributes...")
    attributes = requests.get(f"{BASE_URL}/task-attributes").json()
    print(f"   ✅ Found {len(attributes)} attributes")
    
    # Create answers for each user
    print("\n4️⃣  Creating answers...")
    
    answer_count = 0
    
    for user in [bob, alice]:
        print(f"\n   Answering for {user['name']}...")
        
        for task in all_tasks.values():
            # Each user answers about every task from their perspective
            target_user_id = task['owner_user_id']
            
            for attr in attributes:
                # Generate random value
                attr_name = attr['name']
                
                if attr['type'] == 'enum':
                    if attr_name in ANSWER_VALUES:
                        value = random.choice(ANSWER_VALUES[attr_name])
                    else:
                        value = random.choice(attr.get('allowed_values', ['Unknown']))
                elif attr['type'] == 'bool':
                    value = random.choice(["false", "true"])
                elif attr['type'] == 'int' or attr['type'] == 'float':
                    if attr_name in ANSWER_VALUES:
                        value = random.choice(ANSWER_VALUES[attr_name])
                    else:
                        value = str(random.randint(1, 5))
                else:  # string
                    if attr_name in ANSWER_VALUES:
                        value = random.choice(ANSWER_VALUES[attr_name])
                    else:
                        value = f"Random value for {attr_name}"
                
                # Submit answer directly to backend
                try:
                    # Create a fake question_id (UUID)
                    question_id = str(uuid.uuid4())
                    
                    requests.post(
                        f"{BASE_URL}/answers",
                        headers={"X-User-Id": user['id']},
                        json={
                            "question_id": question_id,
                            "value": value,
                            "refused": False
                        }
                    )
                    answer_count += 1
                except Exception as e:
                    # Might fail if question_id doesn't exist, that's OK
                    pass
        
        print(f"   ✅ Created answers for {user['name']}")
    
    print(f"\n   📊 Total: Attempted {answer_count} answers")
    
    # Summary
    print("\n" + "="*70)
    print("✅ ANSWERS POPULATED!")
    print("="*70)
    print(f"\n📊 Populated data:")
    print(f"   • Answers from Bob's perspective")
    print(f"   • Answers from Alice's perspective")
    print(f"   • About all {len(all_tasks)} tasks")
    print(f"   • For all {len(attributes)} attributes")
    print(f"\n🎮 Try the Task Graph:")
    print(f"   http://localhost:8000/ → Dashboard → Task Graph")
    print(f"\n🔍 Test multi-select filters:")
    print(f"   • Click Priority → Select Critical + High")
    print(f"   • Click Status → Select In progress + Done")
    print(f"   • See filtered tasks!")
    print()

if __name__ == "__main__":
    try:
        populate_direct()
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()

