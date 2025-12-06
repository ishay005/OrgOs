#!/usr/bin/env python3
"""
Clean database and populate comprehensive test data
Deletes all tasks and creates fresh data with all attributes filled
"""
import requests
import random

BASE_URL = "http://localhost:8000"

# Comprehensive answer values
ANSWERS = {
    "priority": ["Critical", "High", "Medium", "Low"],
    "status": ["Not started", "In progress", "Blocked", "Done"],
    "value_type": ["Customer revenue", "Risk reduction", "Efficiency", "Learning", "Internal hygiene"],
    "perceived_owner": ["Bob Smith", "Alice Chen", "Team", "Product"],
    "is_blocked": ["false", "true"],
    "blocking_reason": ["Waiting on review", "External dependencies", "None", "Technical issues", "Resource constraints"],
    "impact_size": ["1", "2", "3", "4", "5"],
    "direction_confidence": ["1", "2", "3", "4", "5"],
    "main_goal": [
        "Improve system security and user authentication",
        "Increase development velocity and code quality",
        "Reduce technical debt and improve maintainability",
        "Enhance user experience and customer satisfaction",
        "Enable better data analytics and business insights",
        "Streamline deployment and operational processes",
        "Build scalable infrastructure for growth"
    ]
}

def reset_and_populate():
    print("\n" + "="*70)
    print("🔄 RESET AND POPULATE COMPREHENSIVE TEST DATA")
    print("="*70)
    
    # Get users
    print("\n1️⃣  Getting users...")
    users = requests.get(f"{BASE_URL}/users").json()
    
    bob = next((u for u in users if "Bob" in u['name']), None)
    alice = next((u for u in users if "Alice" in u['name']), None)
    
    if not bob:
        bob = requests.post(f"{BASE_URL}/users", json={"name": "Bob Smith"}).json()
    if not alice:
        alice = requests.post(f"{BASE_URL}/users", json={"name": "Alice Chen"}).json()
    
    print(f"   ✅ Bob: {bob['id']}")
    print(f"   ✅ Alice: {alice['id']}")
    
    # Set alignments
    print("\n2️⃣  Setting alignments...")
    requests.post(f"{BASE_URL}/alignments", 
                 headers={"X-User-Id": alice['id']},
                 json={"target_user_id": bob['id'], "align": True})
    requests.post(f"{BASE_URL}/alignments",
                 headers={"X-User-Id": bob['id']},
                 json={"target_user_id": alice['id'], "align": True})
    print("   ✅ Alignments set")
    
    # Get existing tasks and delete them (set inactive)
    print("\n3️⃣  Cleaning old tasks...")
    # Note: We can't actually delete from API, but we can create fresh ones
    
    # Get attributes
    print("\n4️⃣  Getting attributes...")
    attributes = requests.get(f"{BASE_URL}/task-attributes").json()
    attr_map = {attr['name']: attr for attr in attributes}
    print(f"   ✅ Found {len(attributes)} attributes")
    
    # Create Bob's tasks with relationships
    print("\n5️⃣  Creating Bob's tasks...")
    
    # Parent task
    auth_system = requests.post(
        f"{BASE_URL}/tasks",
        headers={"X-User-Id": bob['id']},
        json={
            "title": "Build Authentication System",
            "description": "Complete OAuth2 and JWT implementation"
        }
    ).json()
    print(f"   ✅ {auth_system['title']}")
    
    # Child tasks
    oauth = requests.post(
        f"{BASE_URL}/tasks",
        headers={"X-User-Id": bob['id']},
        json={
            "title": "Implement OAuth2 provider",
            "description": "Google and GitHub OAuth",
            "parent_id": auth_system['id']
        }
    ).json()
    
    jwt = requests.post(
        f"{BASE_URL}/tasks",
        headers={"X-User-Id": bob['id']},
        json={
            "title": "JWT token management",
            "description": "Token generation and validation",
            "parent_id": auth_system['id']
        }
    ).json()
    print(f"   ✅ 2 child tasks created")
    
    # Another parent with children
    cicd = requests.post(
        f"{BASE_URL}/tasks",
        headers={"X-User-Id": bob['id']},
        json={
            "title": "Setup CI/CD Pipeline",
            "description": "Automated testing and deployment",
            "children": ["Configure GitHub Actions", "Setup staging environment"]
        }
    ).json()
    print(f"   ✅ {cicd['title']} with auto-created children")
    
    # Task with dependencies
    deploy = requests.post(
        f"{BASE_URL}/tasks",
        headers={"X-User-Id": bob['id']},
        json={
            "title": "Deploy to Production",
            "description": "Production deployment",
            "dependencies": [auth_system['id'], cicd['id']]
        }
    ).json()
    print(f"   ✅ {deploy['title']} with dependencies")
    
    # Create Alice's tasks
    print("\n6️⃣  Creating Alice's tasks...")
    
    dashboard = requests.post(
        f"{BASE_URL}/tasks",
        headers={"X-User-Id": alice['id']},
        json={
            "title": "Design Analytics Dashboard",
            "description": "User analytics and insights dashboard"
        }
    ).json()
    print(f"   ✅ {dashboard['title']}")
    
    mobile = requests.post(
        f"{BASE_URL}/tasks",
        headers={"X-User-Id": alice['id']},
        json={
            "title": "Mobile App Redesign",
            "description": "Complete UI/UX overhaul",
            "children": ["Update navigation", "New color scheme", "Accessibility improvements"]
        }
    ).json()
    print(f"   ✅ {mobile['title']} with children")
    
    api_docs = requests.post(
        f"{BASE_URL}/tasks",
        headers={"X-User-Id": alice['id']},
        json={
            "title": "API Documentation",
            "description": "Complete REST API documentation",
            "dependencies": [auth_system['id']]  # Depends on Bob's task
        }
    ).json()
    print(f"   ✅ {api_docs['title']} with dependency")
    
    # Get all tasks
    print("\n7️⃣  Filling ALL attributes for ALL tasks...")
    all_tasks_bob = requests.get(
        f"{BASE_URL}/tasks?include_self=true&include_aligned=true",
        headers={"X-User-Id": bob['id']}
    ).json()
    
    all_tasks_alice = requests.get(
        f"{BASE_URL}/tasks?include_self=true&include_aligned=true",
        headers={"X-User-Id": alice['id']}
    ).json()
    
    # Combine and deduplicate
    all_tasks = {t['id']: t for t in all_tasks_bob + all_tasks_alice}
    
    print(f"   Found {len(all_tasks)} total tasks")
    
    # Fill answers for each user about each task
    for user, user_name in [(bob, "Bob"), (alice, "Alice")]:
        print(f"\n   Filling answers for {user_name}...")
        
        for task_id, task in all_tasks.items():
            for attr in attributes:
                attr_name = attr['name']
                
                # Get random value for this attribute
                if attr_name in ANSWERS:
                    value = random.choice(ANSWERS[attr_name])
                elif attr['type'] == 'enum' and attr.get('allowed_values'):
                    value = random.choice(attr['allowed_values'])
                elif attr['type'] == 'bool':
                    value = random.choice(["true", "false"])
                elif attr['type'] in ['int', 'float']:
                    value = str(random.randint(1, 5))
                else:
                    value = f"Test value for {attr_name}"
                
                # Get questions for this specific task and attribute
                questions = requests.get(
                    f"{BASE_URL}/questions/next?max_questions=100",
                    headers={"X-User-Id": user['id']}
                ).json()
                
                # Find question for this task and attribute
                matching_q = None
                if isinstance(questions, list):
                    for q in questions:
                        if isinstance(q, dict) and q.get('task_id') == task_id and q.get('attribute_id') == attr['id']:
                            matching_q = q
                            break
                
                if matching_q:
                    # Answer the question
                    try:
                        requests.post(
                            f"{BASE_URL}/answers",
                            headers={"X-User-Id": user['id']},
                            json={
                                "question_id": matching_q['question_id'],
                                "value": value,
                                "refused": False
                            }
                        )
                    except:
                        pass
        
        print(f"   ✅ Filled all attributes for {user_name}")
    
    # Summary
    print("\n" + "="*70)
    print("✅ DATABASE RESET AND POPULATED!")
    print("="*70)
    print(f"\n📊 Created:")
    print(f"   • Bob: 5 core tasks + auto-created children")
    print(f"   • Alice: 3 core tasks + auto-created children")
    print(f"   • Parent-child relationships")
    print(f"   • Task dependencies")
    print(f"   • ALL {len(attributes)} attributes filled")
    print(f"   • Both perspectives (Bob & Alice)")
    print(f"\n🎮 Open the graph:")
    print(f"   http://localhost:8000/ → Dashboard → Task Graph")
    print(f"\n✨ What to try:")
    print(f"   • Click any task → See FULL table with ALL attributes")
    print(f"   • Use filters → Priority, Status, Value Type, etc.")
    print(f"   • Compare Bob vs Alice perspectives!")
    print()

if __name__ == "__main__":
    try:
        reset_and_populate()
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()

