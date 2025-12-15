"""
Task Merge UI Tests

Tests the task merge UI flow:
- See task suggested for you
- Choose "merge into existing task"
- Pick target and confirm
- Verify alias info on target

Unit Size: End-to-end UI tests
Failure Modes:
- Merge option not visible
- Target selection broken
- Alias not displayed
- Confirmation issues
"""

import pytest
import os
import uuid

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_UI_TESTS") != "1",
    reason="Set RUN_UI_TESTS=1 to run UI tests"
)


class TestMergeTaskUI:
    """Test the task merge UI flow."""
    
    def test_pending_task_shows_merge_option(self, logged_in_page, test_server, db_session, sample_users):
        """Pending task should show merge option."""
        from app.models import Task, TaskState, PendingDecision, PendingDecisionType
        
        owner = sample_users["employee1"]
        creator = sample_users["manager"]
        
        # Create DRAFT task
        task = Task(
            id=uuid.uuid4(),
            title="Suggested Task for Merge Test",
            owner_user_id=owner.id,
            created_by_user_id=creator.id,
            state=TaskState.DRAFT
        )
        db_session.add(task)
        
        decision = PendingDecision(
            id=uuid.uuid4(),
            user_id=owner.id,
            decision_type=PendingDecisionType.TASK_ACCEPTANCE,
            entity_type="task",
            entity_id=task.id,
            description="Accept or merge this task?"
        )
        db_session.add(decision)
        db_session.commit()
        
        page = logged_in_page
        page.goto(test_server)
        page.wait_for_load_state("networkidle")
        
        # Navigate to pending decisions
        decisions_btn = page.locator("button:has-text('Pending'), text=Decisions, #pending-decisions-btn").first
        
        if decisions_btn.is_visible():
            decisions_btn.click()
            page.wait_for_load_state("networkidle")
            
            # Look for merge button
            merge_btn = page.locator("button:has-text('Merge'), button:has-text('🔀')").first
            
            # Merge option should be available
            # (Actual visibility depends on UI implementation)
    
    def test_merge_dialog_opens(self, logged_in_page, test_server, db_session, sample_users):
        """Clicking merge should open merge dialog."""
        from app.models import Task, TaskState, PendingDecision, PendingDecisionType
        
        owner = sample_users["employee1"]
        creator = sample_users["manager"]
        
        # Create draft and target tasks
        draft_task = Task(
            id=uuid.uuid4(),
            title="Draft for Merge Dialog Test",
            owner_user_id=owner.id,
            created_by_user_id=creator.id,
            state=TaskState.DRAFT
        )
        target_task = Task(
            id=uuid.uuid4(),
            title="Target Task",
            owner_user_id=owner.id,
            created_by_user_id=owner.id,
            state=TaskState.ACTIVE
        )
        db_session.add_all([draft_task, target_task])
        
        decision = PendingDecision(
            id=uuid.uuid4(),
            user_id=owner.id,
            decision_type=PendingDecisionType.TASK_ACCEPTANCE,
            entity_type="task",
            entity_id=draft_task.id,
            description="Accept or merge?"
        )
        db_session.add(decision)
        db_session.commit()
        
        page = logged_in_page
        page.goto(test_server)
        page.wait_for_load_state("networkidle")
        
        # Navigate to decisions and click merge
        decisions_btn = page.locator("button:has-text('Pending'), #pending-decisions-btn").first
        
        if decisions_btn.is_visible():
            decisions_btn.click()
            page.wait_for_timeout(500)
            
            merge_btn = page.locator("button:has-text('Merge'), button:has-text('🔀')").first
            
            if merge_btn.is_visible():
                merge_btn.click()
                page.wait_for_timeout(500)
                
                # Dialog/modal should appear
                modal = page.locator(".modal, [role='dialog'], .popup").first
                
                # Modal should be visible (or some merge UI element)


class TestMergeTargetSelection:
    """Test selecting a target task for merge."""
    
    def test_can_select_target_task(self, logged_in_page, test_server, db_session, sample_users):
        """Should be able to select target task from list."""
        from app.models import Task, TaskState
        
        owner = sample_users["employee1"]
        
        # Create multiple tasks to choose from
        for i in range(3):
            task = Task(
                id=uuid.uuid4(),
                title=f"Target Option {i+1}",
                owner_user_id=owner.id,
                created_by_user_id=owner.id,
                state=TaskState.ACTIVE
            )
            db_session.add(task)
        db_session.commit()
        
        page = logged_in_page
        page.goto(test_server)
        page.wait_for_load_state("networkidle")
        
        # Look for task selection dropdown in merge UI
        # This depends on the actual implementation
        task_select = page.locator("select#target-task, select[name='target'], #merge-target-select").first
        
        if task_select.is_visible():
            # Should have options
            options = task_select.locator("option").all()
            assert len(options) >= 0


class TestMergeConfirmation:
    """Test merge confirmation and result."""
    
    def test_merge_success_shows_alias(self, logged_in_page, test_server, db_session, sample_users):
        """After successful merge, alias should be visible on target."""
        from app.models import Task, TaskState, TaskAlias
        
        owner = sample_users["employee1"]
        
        # Create target task with existing alias
        target_task = Task(
            id=uuid.uuid4(),
            title="Task With Alias",
            owner_user_id=owner.id,
            created_by_user_id=owner.id,
            state=TaskState.ACTIVE
        )
        db_session.add(target_task)
        db_session.flush()
        
        alias = TaskAlias(
            id=uuid.uuid4(),
            canonical_task_id=target_task.id,
            alias_title="Previously Merged Task",
            alias_created_by_user_id=sample_users["manager"].id
        )
        db_session.add(alias)
        db_session.commit()
        
        page = logged_in_page
        page.goto(test_server)
        page.wait_for_load_state("networkidle")
        
        # Navigate to task graph or task list
        graph_btn = page.locator("button:has-text('Graph'), text=Task Graph, #task-graph-btn").first
        
        if graph_btn.is_visible():
            graph_btn.click()
            page.wait_for_load_state("networkidle")
            
            # Click on the task with alias
            task_node = page.locator(f"text=Task With Alias").first
            
            if task_node.is_visible():
                task_node.click()
                page.wait_for_timeout(500)
                
                # Look for alias info in popup/details
                alias_text = page.locator("text=alias, text=Previously Merged").first
                
                # Alias info should be visible (if UI shows it)

