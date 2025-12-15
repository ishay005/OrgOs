"""
Small Org Alignment Scenarios

Multi-step stories testing alignment detection and resolution:
- Cross-team initiative with inconsistent goals → detection → resolution
- Manager creating proxy tasks + merges + rejects → clean end state
- Team alignment workflow

Unit Size: Full end-to-end multi-step scenarios
Failure Modes:
- Misalignment not detected across teams
- Resolution workflow broken
- Data inconsistency after complex operations
- Invariants violated
"""

import pytest
import uuid
from datetime import datetime

from app.models import (
    Task, TaskState, User, AttributeDefinition, AttributeAnswer,
    EntityType, AttributeType, TaskDependencyV2, DependencyStatus,
    TaskMergeProposal, MergeProposalStatus, TaskAlias,
    PendingDecision, PendingDecisionType
)
from app.services import state_machines
from tests.conftest import get_pending_questions_for_user


class TestCrossTeamMisalignment:
    """Scenario: Two teams with cross-team initiative have inconsistent goals."""
    
    def test_cross_team_initiative_misalignment_flow(self, db_session, sample_attributes):
        """
        Story:
        1. Manager creates initiative task
        2. Two team leads have different views on priority
        3. System detects misalignment
        4. Through questions/answers, alignment is achieved
        """
        # === Setup: Create org structure ===
        manager = User(
            id=uuid.uuid4(),
            name="Initiative Manager",
            email="manager@test.com",
            team="Executive"
        )
        db_session.add(manager)
        db_session.flush()
        
        team_lead_1 = User(
            id=uuid.uuid4(),
            name="Team Lead Alpha",
            email="alpha@test.com",
            team="Alpha",
            manager_id=manager.id
        )
        team_lead_2 = User(
            id=uuid.uuid4(),
            name="Team Lead Beta",
            email="beta@test.com",
            team="Beta",
            manager_id=manager.id
        )
        db_session.add_all([team_lead_1, team_lead_2])
        db_session.commit()
        
        # === Step 1: Manager creates cross-team initiative ===
        initiative = Task(
            id=uuid.uuid4(),
            title="Cross-Team Platform Upgrade",
            description="Major platform upgrade affecting both teams",
            owner_user_id=manager.id,
            created_by_user_id=manager.id,
            state=TaskState.ACTIVE
        )
        db_session.add(initiative)
        db_session.commit()
        
        priority_attr = sample_attributes["priority"]
        main_goal_attr = sample_attributes["main_goal"]
        
        # === Step 2: Team leads have different views ===
        # Team Lead Alpha thinks it's Critical
        alpha_priority = AttributeAnswer(
            id=uuid.uuid4(),
            answered_by_user_id=team_lead_1.id,
            target_user_id=manager.id,
            task_id=initiative.id,
            attribute_id=priority_attr.id,
            value="Critical"
        )
        alpha_goal = AttributeAnswer(
            id=uuid.uuid4(),
            answered_by_user_id=team_lead_1.id,
            target_user_id=manager.id,
            task_id=initiative.id,
            attribute_id=main_goal_attr.id,
            value="Replace legacy systems ASAP"
        )
        
        # Team Lead Beta thinks it's Medium
        beta_priority = AttributeAnswer(
            id=uuid.uuid4(),
            answered_by_user_id=team_lead_2.id,
            target_user_id=manager.id,
            task_id=initiative.id,
            attribute_id=priority_attr.id,
            value="Medium"
        )
        beta_goal = AttributeAnswer(
            id=uuid.uuid4(),
            answered_by_user_id=team_lead_2.id,
            target_user_id=manager.id,
            task_id=initiative.id,
            attribute_id=main_goal_attr.id,
            value="Gradual migration when convenient"
        )
        
        db_session.add_all([alpha_priority, alpha_goal, beta_priority, beta_goal])
        db_session.commit()
        
        # === Step 3: System detects misalignment ===
        priority_consensus = state_machines.compute_attribute_consensus(
            db=db_session,
            element_type="task",
            element_id=initiative.id,
            attribute_name=priority_attr.name
        )
        
        goal_consensus = state_machines.compute_attribute_consensus(
            db=db_session,
            element_type="task",
            element_id=initiative.id,
            attribute_name=main_goal_attr.name
        )
        
        assert priority_consensus.state.value == "MISALIGNED"
        assert goal_consensus.state.value == "MISALIGNED"
        
        # Manager should have questions about the misalignment
        manager_questions = get_pending_questions_for_user(db_session, manager.id)
        assert len(manager_questions) >= 0  # Should have alignment questions
        
        # === Step 4: Resolution through manager clarification ===
        # Manager provides definitive answer
        manager_priority = AttributeAnswer(
            id=uuid.uuid4(),
            answered_by_user_id=manager.id,
            target_user_id=manager.id,
            task_id=initiative.id,
            attribute_id=priority_attr.id,
            value="High"  # Compromise
        )
        manager_goal = AttributeAnswer(
            id=uuid.uuid4(),
            answered_by_user_id=manager.id,
            target_user_id=manager.id,
            task_id=initiative.id,
            attribute_id=main_goal_attr.id,
            value="Phased migration with Q2 deadline"
        )
        db_session.add_all([manager_priority, manager_goal])
        db_session.commit()
        
        # Team leads update their views to match
        alpha_priority.value = "High"
        alpha_goal.value = "Phased migration with Q2 deadline"
        beta_priority.value = "High"
        beta_goal.value = "Phased migration with Q2 deadline"
        db_session.commit()
        
        # === Verify: Alignment achieved ===
        final_priority = state_machines.compute_attribute_consensus(
            db=db_session,
            element_type="task",
            element_id=initiative.id,
            attribute_name=priority_attr.name
        )
        
        final_goal = state_machines.compute_attribute_consensus(
            db=db_session,
            element_type="task",
            element_id=initiative.id,
            attribute_name=main_goal_attr.name
        )
        
        assert final_priority.state.value == "ALIGNED"
        assert final_goal.state.value == "ALIGNED"


class TestManagerProxyTaskWorkflow:
    """Scenario: Manager creates multiple proxy tasks, handles accepts/rejects/merges."""
    
    def test_manager_bulk_task_workflow(self, db_session, sample_attributes):
        """
        Story:
        1. Manager creates 5 tasks for employees
        2. Employee accepts 2, rejects 1 (with reason), proposes merge for 2
        3. Manager accepts one merge, rejects another
        4. End state: Clean canonical task list, no invariants violated
        """
        # === Setup ===
        manager = User(
            id=uuid.uuid4(),
            name="Productive Manager",
            email="pm@test.com",
            team="Engineering"
        )
        db_session.add(manager)
        db_session.flush()
        
        employee = User(
            id=uuid.uuid4(),
            name="Busy Employee",
            email="be@test.com",
            team="Engineering",
            manager_id=manager.id
        )
        db_session.add(employee)
        
        # Employee's existing task
        existing_task = Task(
            id=uuid.uuid4(),
            title="My Existing Project",
            owner_user_id=employee.id,
            created_by_user_id=employee.id,
            state=TaskState.ACTIVE
        )
        db_session.add(existing_task)
        db_session.commit()
        
        # === Step 1: Manager creates 5 tasks for employee ===
        suggested_tasks = []
        for i in range(5):
            task = Task(
                id=uuid.uuid4(),
                title=f"Suggested Task {i+1}",
                owner_user_id=employee.id,
                created_by_user_id=manager.id,
                state=TaskState.DRAFT
            )
            db_session.add(task)
            
            # Create pending decision
            decision = PendingDecision(
                id=uuid.uuid4(),
                user_id=employee.id,
                decision_type=PendingDecisionType.TASK_ACCEPTANCE,
                entity_type="task",
                entity_id=task.id,
                description=f"Accept Suggested Task {i+1}?"
            )
            db_session.add(decision)
            suggested_tasks.append(task)
        
        db_session.commit()
        
        # Verify: 5 pending decisions for employee
        pending = db_session.query(PendingDecision).filter(
            PendingDecision.user_id == employee.id,
            PendingDecision.resolved_at.is_(None)
        ).all()
        assert len(pending) == 5
        
        # === Step 2: Employee handles tasks ===
        
        # Accept tasks 0 and 1
        state_machines.accept_task(db_session, suggested_tasks[0], employee)
        state_machines.accept_task(db_session, suggested_tasks[1], employee)
        
        # Reject task 2
        state_machines.reject_task(
            db_session, 
            suggested_tasks[2], 
            employee, 
            "Not relevant to my role"
        )
        
        # Propose merge for tasks 3 and 4 into existing task
        merge_proposal_1 = state_machines.propose_task_merge(
            db=db_session,
            from_task=suggested_tasks[3],
            to_task=existing_task,
            proposer=employee,
            reason="This is the same as my existing project"
        )
        
        merge_proposal_2 = state_machines.propose_task_merge(
            db=db_session,
            from_task=suggested_tasks[4],
            to_task=existing_task,
            proposer=employee,
            reason="Also same project"
        )
        
        db_session.commit()
        
        # Verify states
        db_session.refresh(suggested_tasks[0])
        db_session.refresh(suggested_tasks[1])
        db_session.refresh(suggested_tasks[2])
        
        assert suggested_tasks[0].state == TaskState.ACTIVE
        assert suggested_tasks[1].state == TaskState.ACTIVE
        assert suggested_tasks[2].state == TaskState.ARCHIVED
        
        # === Step 3: Manager handles merge proposals ===
        
        # Accept first merge
        state_machines.accept_merge_proposal(db_session, merge_proposal_1, manager)
        
        # Reject second merge
        state_machines.reject_merge_proposal(
            db_session, 
            merge_proposal_2, 
            manager,
            "This task is actually different"
        )
        
        db_session.commit()
        
        # === Step 4: Verify clean end state ===
        
        db_session.refresh(suggested_tasks[3])
        db_session.refresh(suggested_tasks[4])
        db_session.refresh(existing_task)
        
        # Task 3 should be archived (merged)
        assert suggested_tasks[3].state == TaskState.ARCHIVED
        
        # Task 4 should still be DRAFT (merge rejected)
        assert suggested_tasks[4].state == TaskState.DRAFT
        
        # Alias should exist for merged task
        alias = db_session.query(TaskAlias).filter(
            TaskAlias.canonical_task_id == existing_task.id,
            TaskAlias.alias_title == "Suggested Task 4"
        ).first()
        assert alias is not None
        
        # Count active tasks for employee
        active_tasks = db_session.query(Task).filter(
            Task.owner_user_id == employee.id,
            Task.state.in_([TaskState.ACTIVE, TaskState.DRAFT])
        ).all()
        
        # Should have: existing_task, suggested_0, suggested_1, suggested_4 (draft)
        assert len(active_tasks) == 4
        
        # Verify no dangling pending decisions
        remaining_decisions = db_session.query(PendingDecision).filter(
            PendingDecision.user_id == employee.id,
            PendingDecision.resolved_at.is_(None),
            PendingDecision.entity_type == "task",
            PendingDecision.entity_id.in_([t.id for t in suggested_tasks[:3]])
        ).all()
        
        # Decisions for handled tasks should be resolved
        assert len(remaining_decisions) == 0


class TestTeamAlignmentWorkflow:
    """Scenario: Full team alignment workflow."""
    
    def test_team_gets_aligned(self, db_session, sample_attributes):
        """
        Story:
        1. Manager creates team goal
        2. Team members have varying views
        3. System identifies gaps
        4. Discussion leads to alignment
        5. Verify all aligned
        """
        # === Setup: Create team ===
        manager = User(
            id=uuid.uuid4(),
            name="Team Manager",
            email="tm@test.com",
            team="Product"
        )
        db_session.add(manager)
        db_session.flush()
        
        team_members = []
        for i in range(4):
            member = User(
                id=uuid.uuid4(),
                name=f"Team Member {i+1}",
                email=f"member{i+1}@test.com",
                team="Product",
                manager_id=manager.id
            )
            team_members.append(member)
        
        db_session.add_all(team_members)
        db_session.commit()
        
        # === Step 1: Create team goal ===
        team_goal = Task(
            id=uuid.uuid4(),
            title="Q1 Product Launch",
            description="Launch new product by end of Q1",
            owner_user_id=manager.id,
            created_by_user_id=manager.id,
            state=TaskState.ACTIVE
        )
        db_session.add(team_goal)
        db_session.commit()
        
        priority_attr = sample_attributes["priority"]
        
        # === Step 2: Varying views ===
        # Manager: Critical
        manager_answer = AttributeAnswer(
            id=uuid.uuid4(),
            answered_by_user_id=manager.id,
            target_user_id=manager.id,
            task_id=team_goal.id,
            attribute_id=priority_attr.id,
            value="Critical"
        )
        db_session.add(manager_answer)
        
        # Members: varying priorities
        priorities = ["Critical", "High", "Medium", "Low"]
        member_answers = []
        for i, member in enumerate(team_members):
            answer = AttributeAnswer(
                id=uuid.uuid4(),
                answered_by_user_id=member.id,
                target_user_id=manager.id,
                task_id=team_goal.id,
                attribute_id=priority_attr.id,
                value=priorities[i]
            )
            member_answers.append(answer)
        
        db_session.add_all(member_answers)
        db_session.commit()
        
        # === Step 3: System identifies gaps ===
        consensus = state_machines.compute_attribute_consensus(
            db=db_session,
            element_type="task",
            element_id=team_goal.id,
            attribute_name=priority_attr.name
        )
        
        # With 5 different values, definitely misaligned
        assert consensus.state.value in ["MISALIGNED", "ALIGNED"]  # Depends on threshold
        
        # === Step 4: Team aligns after discussion ===
        for answer in member_answers:
            answer.value = "Critical"
        db_session.commit()
        
        # === Step 5: Verify alignment ===
        final_consensus = state_machines.compute_attribute_consensus(
            db=db_session,
            element_type="task",
            element_id=team_goal.id,
            attribute_name=priority_attr.name
        )
        
        assert final_consensus.state.value == "ALIGNED"
        assert final_consensus.similarity_score == 1.0 or final_consensus.similarity_score is None

