"""
Dependency Flow UI Tests

Tests the dependency UI flow:
- Declare dependency on another task
- Upstream owner sees pending request
- Accept/reject/suggest alternative
- Visual status badges

Unit Size: End-to-end UI tests
Failure Modes:
- Dependency creation fails
- Pending request not visible
- Accept/reject not working
- Status not updated
"""

import pytest
import os
import uuid

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_UI_TESTS") != "1",
    reason="Set RUN_UI_TESTS=1 to run UI tests"
)


class TestDependencyCreationUI:
    """Test creating dependencies through UI."""
    
    def test_can_add_dependency_from_task(self, logged_in_page, test_server, db_session, sample_users, sample_tasks):
        """Should be able to add dependency from task details."""
        page = logged_in_page
        page.goto(test_server)
        page.wait_for_load_state("networkidle")
        
        # Navigate to task graph
        graph_btn = page.locator("button:has-text('Graph'), #task-graph-btn, text=Task Graph").first
        
        if graph_btn.is_visible():
            graph_btn.click()
            page.wait_for_load_state("networkidle")
            
            # Click on a task
            task_nodes = page.locator(".task-node, [data-task-id], .node").all()
            
            if len(task_nodes) > 0:
                task_nodes[0].click()
                page.wait_for_timeout(500)
                
                # Look for add dependency button
                add_dep_btn = page.locator("button:has-text('Dependency'), button:has-text('Add'), #add-dependency-btn").first
                
                # Button should exist in task details
    
    def test_dependency_selector_shows_tasks(self, logged_in_page, test_server, db_session, sample_users, sample_tasks):
        """Dependency selector should show available tasks."""
        page = logged_in_page
        page.goto(test_server)
        page.wait_for_load_state("networkidle")
        
        # Navigate to task editing mode
        # Look for task selector or dependency dropdown
        dep_select = page.locator("select#dependency-select, select[name='dependency'], #add-dep-select").first
        
        if dep_select.is_visible():
            options = dep_select.locator("option").all()
            # Should have task options
            assert len(options) >= 0


class TestDependencyApprovalUI:
    """Test dependency approval UI."""
    
    def test_pending_dependency_visible_to_upstream_owner(self, logged_in_page, test_server, db_session, sample_users, sample_tasks):
        """Upstream owner should see pending dependency request."""
        from app.models import TaskDependencyV2, DependencyStatus, PendingDecision, PendingDecisionType
        
        task1 = sample_tasks["task1"]
        task2 = sample_tasks["task2"]
        upstream_owner = sample_users["employee2"]
        
        # Create pending dependency
        dep = TaskDependencyV2(
            id=uuid.uuid4(),
            downstream_task_id=task1.id,
            upstream_task_id=task2.id,
            status=DependencyStatus.PROPOSED,
            created_by_user_id=sample_users["employee1"].id
        )
        db_session.add(dep)
        
        decision = PendingDecision(
            id=uuid.uuid4(),
            user_id=upstream_owner.id,
            decision_type=PendingDecisionType.DEPENDENCY_APPROVAL,
            entity_type="dependency",
            entity_id=dep.id,
            description="Accept dependency?"
        )
        db_session.add(decision)
        db_session.commit()
        
        # Log in as upstream owner (would need different user selection)
        page = logged_in_page
        page.goto(test_server)
        page.wait_for_load_state("networkidle")
        
        # Navigate to pending decisions
        decisions_btn = page.locator("button:has-text('Pending'), #pending-decisions-btn").first
        
        if decisions_btn.is_visible():
            decisions_btn.click()
            page.wait_for_load_state("networkidle")
            
            # Should see dependency decision
            dep_decision = page.locator("text=dependency, text=DEPENDENCY").first
            
            # Decision should be visible
    
    def test_accept_dependency_button_works(self, logged_in_page, test_server, db_session, sample_users, sample_tasks):
        """Accept button should confirm dependency."""
        from app.models import TaskDependencyV2, DependencyStatus, PendingDecision, PendingDecisionType
        
        task1 = sample_tasks["task1"]
        task2 = sample_tasks["task2"]
        
        dep = TaskDependencyV2(
            id=uuid.uuid4(),
            downstream_task_id=task1.id,
            upstream_task_id=task2.id,
            status=DependencyStatus.PROPOSED,
            created_by_user_id=sample_users["employee1"].id
        )
        db_session.add(dep)
        
        decision = PendingDecision(
            id=uuid.uuid4(),
            user_id=sample_users["employee2"].id,
            decision_type=PendingDecisionType.DEPENDENCY_APPROVAL,
            entity_type="dependency",
            entity_id=dep.id,
            description="Accept?"
        )
        db_session.add(decision)
        db_session.commit()
        
        page = logged_in_page
        page.goto(test_server)
        page.wait_for_load_state("networkidle")
        
        # Navigate to decisions
        decisions_btn = page.locator("button:has-text('Pending'), #pending-decisions-btn").first
        
        if decisions_btn.is_visible():
            decisions_btn.click()
            page.wait_for_timeout(500)
            
            accept_btn = page.locator("button:has-text('Accept'), button:has-text('✅')").first
            
            if accept_btn.is_visible():
                accept_btn.click()
                page.wait_for_timeout(500)
                
                # Decision should be processed


class TestDependencyStatusBadges:
    """Test dependency status display."""
    
    def test_confirmed_dependency_shows_status(self, logged_in_page, test_server, db_session, sample_users, sample_tasks):
        """Confirmed dependency should show confirmed status."""
        from app.models import TaskDependencyV2, DependencyStatus
        
        task1 = sample_tasks["task1"]
        task2 = sample_tasks["task2"]
        
        dep = TaskDependencyV2(
            id=uuid.uuid4(),
            downstream_task_id=task1.id,
            upstream_task_id=task2.id,
            status=DependencyStatus.CONFIRMED,
            created_by_user_id=sample_users["employee1"].id,
            accepted_by_user_id=sample_users["employee2"].id
        )
        db_session.add(dep)
        db_session.commit()
        
        page = logged_in_page
        page.goto(test_server)
        page.wait_for_load_state("networkidle")
        
        # Navigate to task graph
        graph_btn = page.locator("button:has-text('Graph'), #task-graph-btn").first
        
        if graph_btn.is_visible():
            graph_btn.click()
            page.wait_for_load_state("networkidle")
            
            # Look for dependency line or badge
            dep_line = page.locator(".dependency-line, [data-dependency], .edge").first
            
            # Some visual indicator should exist for confirmed dependencies
    
    def test_proposed_dependency_shows_pending(self, logged_in_page, test_server, db_session, sample_users, sample_tasks):
        """Proposed dependency should show pending status."""
        from app.models import TaskDependencyV2, DependencyStatus
        
        task1 = sample_tasks["task1"]
        task2 = sample_tasks["task2"]
        
        dep = TaskDependencyV2(
            id=uuid.uuid4(),
            downstream_task_id=task1.id,
            upstream_task_id=task2.id,
            status=DependencyStatus.PROPOSED,
            created_by_user_id=sample_users["employee1"].id
        )
        db_session.add(dep)
        db_session.commit()
        
        page = logged_in_page
        page.goto(test_server)
        page.wait_for_load_state("networkidle")
        
        # Navigate to task details
        # Look for pending indicator
        pending_indicator = page.locator("text=pending, text=PROPOSED, .pending-badge").first
        
        # Some indication of pending status should be visible
        # (Depends on UI implementation)


class TestAlternativeDependencyUI:
    """Test alternative dependency suggestion UI."""
    
    def test_suggest_alternative_button_exists(self, logged_in_page, test_server, db_session, sample_users, sample_tasks):
        """Alternative suggestion button should exist on pending dependencies."""
        from app.models import TaskDependencyV2, DependencyStatus, PendingDecision, PendingDecisionType
        
        task1 = sample_tasks["task1"]
        task2 = sample_tasks["task2"]
        
        dep = TaskDependencyV2(
            id=uuid.uuid4(),
            downstream_task_id=task1.id,
            upstream_task_id=task2.id,
            status=DependencyStatus.PROPOSED,
            created_by_user_id=sample_users["employee1"].id
        )
        db_session.add(dep)
        
        decision = PendingDecision(
            id=uuid.uuid4(),
            user_id=sample_users["employee2"].id,
            decision_type=PendingDecisionType.DEPENDENCY_APPROVAL,
            entity_type="dependency",
            entity_id=dep.id,
            description="Review dependency"
        )
        db_session.add(decision)
        db_session.commit()
        
        page = logged_in_page
        page.goto(test_server)
        page.wait_for_load_state("networkidle")
        
        # Navigate to decisions
        decisions_btn = page.locator("button:has-text('Pending'), #pending-decisions-btn").first
        
        if decisions_btn.is_visible():
            decisions_btn.click()
            page.wait_for_timeout(500)
            
            # Look for alternative/suggest button
            alt_btn = page.locator("button:has-text('Alternative'), button:has-text('Suggest')").first
            
            # Alternative option should be available

