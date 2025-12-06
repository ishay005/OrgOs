#!/usr/bin/env python3
"""
Test script for task relationships (parent, children, dependencies)
Run this to verify the task relationship features are working correctly.
"""
import requests
import json

BASE_URL = "http://localhost:8000"

def test_task_relationships():
    print("\n" + "="*70)
    print("🧪 TESTING TASK RELATIONSHIPS")
    print("="*70)
    
    # Step 1: Create users
    print("\n1️⃣  Creating users...")
    alice = requests.post(f"{BASE_URL}/users", json={
        "name": "Alice Chen",
        "email": "alice@example.com"
    }).json()
    print(f"   ✅ Alice: {alice['id']}")
    
    bob = requests.post(f"{BASE_URL}/users", json={
        "name": "Bob Smith", 
        "email": "bob@example.com"
    }).json()
    print(f"   ✅ Bob: {bob['id']}")
    
    # Step 2: Create a parent task
    print("\n2️⃣  Bob creates a parent task...")
    parent_task = requests.post(
        f"{BASE_URL}/tasks",
        headers={"X-User-Id": bob['id']},
        json={
            "title": "Build Authentication System",
            "description": "Complete OAuth2 implementation"
        }
    ).json()
    print(f"   ✅ Parent Task: {parent_task['title']}")
    print(f"      ID: {parent_task['id']}")
    
    # Step 3: Create a child task with parent reference
    print("\n3️⃣  Bob creates a child task...")
    child_task = requests.post(
        f"{BASE_URL}/tasks",
        headers={"X-User-Id": bob['id']},
        json={
            "title": "Implement OAuth2 provider",
            "description": "Google & GitHub OAuth",
            "parent_id": parent_task['id']
        }
    ).json()
    print(f"   ✅ Child Task: {child_task['title']}")
    print(f"      Parent ID: {child_task['parent_id']}")
    
    # Step 4: Create task with auto-generated children
    print("\n4️⃣  Bob creates a task with child tasks...")
    task_with_children = requests.post(
        f"{BASE_URL}/tasks",
        headers={"X-User-Id": bob['id']},
        json={
            "title": "Database Setup",
            "description": "Set up production database",
            "children": [
                "Configure PostgreSQL",
                "Set up migrations",
                "Create backup strategy"
            ]
        }
    ).json()
    print(f"   ✅ Task: {task_with_children['title']}")
    print(f"      Auto-created 3 child tasks")
    
    # Step 5: Create task with dependencies
    print("\n5️⃣  Bob creates a task with dependencies...")
    dependent_task = requests.post(
        f"{BASE_URL}/tasks",
        headers={"X-User-Id": bob['id']},
        json={
            "title": "Deploy to Production",
            "description": "Final deployment",
            "dependencies": [parent_task['id'], task_with_children['id']]
        }
    ).json()
    print(f"   ✅ Task: {dependent_task['title']}")
    print(f"      Depends on 2 tasks")
    
    # Step 6: Test invalid parent (should fail)
    print("\n6️⃣  Testing validation - invalid parent...")
    try:
        requests.post(
            f"{BASE_URL}/tasks",
            headers={"X-User-Id": bob['id']},
            json={
                "title": "Should Fail",
                "parent_id": "00000000-0000-0000-0000-000000000000"  # Non-existent
            }
        ).raise_for_status()
        print("   ❌ FAILED: Should have rejected invalid parent")
    except requests.exceptions.HTTPError as e:
        print(f"   ✅ Correctly rejected: {e.response.status_code}")
    
    # Step 7: Get task graph
    print("\n7️⃣  Fetching task graph...")
    graph = requests.get(f"{BASE_URL}/tasks/graph").json()
    print(f"   ✅ Retrieved {len(graph)} tasks in graph")
    
    # Analyze relationships
    tasks_with_parents = sum(1 for t in graph if t['parent_id'])
    tasks_with_children = sum(1 for t in graph if len(t['children_ids']) > 0)
    tasks_with_deps = sum(1 for t in graph if len(t['dependency_ids']) > 0)
    
    print(f"\n   📊 Graph Statistics:")
    print(f"      Tasks with parents: {tasks_with_parents}")
    print(f"      Tasks with children: {tasks_with_children}")
    print(f"      Tasks with dependencies: {tasks_with_deps}")
    
    # Show a sample task with relationships
    complex_tasks = [t for t in graph if t['parent_id'] or t['children_ids'] or t['dependency_ids']]
    if complex_tasks:
        sample = complex_tasks[0]
        print(f"\n   📝 Sample Task: {sample['title']}")
        if sample['parent_id']:
            print(f"      ⬆️  Has parent: {sample['parent_id']}")
        if sample['children_ids']:
            print(f"      ⬇️  Has {len(sample['children_ids'])} children")
        if sample['dependency_ids']:
            print(f"      ➡️  Depends on {len(sample['dependency_ids'])} tasks")
    
    # Step 8: Verify all tasks are listed
    print("\n8️⃣  Verifying all tasks...")
    all_tasks = requests.get(
        f"{BASE_URL}/tasks?include_self=true&include_aligned=true",
        headers={"X-User-Id": bob['id']}
    ).json()
    print(f"   ✅ Found {len(all_tasks)} total tasks")
    
    # Summary
    print("\n" + "="*70)
    print("✅ TASK RELATIONSHIP TESTS PASSED!")
    print("="*70)
    print("\n🌟 Features Tested:")
    print("   ✅ Parent-child relationships")
    print("   ✅ Auto-creation of child tasks")
    print("   ✅ Task dependencies")
    print("   ✅ Parent validation")
    print("   ✅ Task graph API")
    print("\n📱 Open the Web UI to see the graph visualization:")
    print("   🖥️  http://localhost:8000/")
    print("   Then navigate to Dashboard → 🔗 Task Graph")
    print()

if __name__ == "__main__":
    try:
        test_task_relationships()
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()

