"""
Task Merge Lifecycle Integration Tests

Tests the full merge lifecycle:
- Propose merge with reason
- Accept merge: creates alias, migrates data
- Reject merge: keeps task separate
- Merge data migration (attributes, dependencies)

Unit Size: Multi-component flow (API + DB + Services)
Failure Modes:
- Merge not creating TaskAlias
- Attributes not migrated
- Dependencies not re-pointed
- Original task not archived
- Merge cycles
"""

import pytest
import uuid
from datetime import datetime

from app.models import (
    Task, TaskState, User, TaskMergeProposal, MergeProposalStatus,
    TaskAlias, AttributeAnswer, TaskDependencyV2, DependencyStatus,
    AttributeDefinition, EntityType, AttributeType
)


class TestMergeProposal:
    """Test merge proposal creation."""
    
    def test_propose_merge(self, test_client, db_session, sample_users, sample_tasks):
        """Owner can propose merging DRAFT task into existing task."""
        manager = sample_users["manager"]
        employee = sample_users["employee1"]
        
        # Create a DRAFT task
        draft_task = Task(
            id=uuid.uuid4(),
            title="Suggested Task",
            owner_user_id=employee.id,
            created_by_user_id=manager.id,
            state=TaskState.DRAFT
        )
        # Target task to merge into
        target_task = Task(
            id=uuid.uuid4(),
            title="Existing Task",
            owner_user_id=employee.id,
            created_by_user_id=employee.id,
            state=TaskState.ACTIVE
        )
        db_session.add_all([draft_task, target_task])
        db_session.commit()
        
        # Propose merge via the task decision endpoint
        response = test_client.post(
            f"/decisions/task/{draft_task.id}",
            json={
                "action": "propose_merge",
                "merge_into_task_id": str(target_task.id),
                "reason": "This is the same as my existing task"
            },
            headers={"X-User-Id": str(employee.id)}
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        # Check merge proposal exists
        proposal = db_session.query(TaskMergeProposal).filter(
            TaskMergeProposal.from_task_id == draft_task.id,
            TaskMergeProposal.to_task_id == target_task.id
        ).first()
        
        assert proposal is not None
        assert proposal.status == MergeProposalStatus.PROPOSED
        assert proposal.proposal_reason == "This is the same as my existing task"
    
    def test_cancel_merge_proposal(self, test_client, db_session, sample_users, sample_tasks):
        """Proposer can cancel their merge proposal."""
        employee = sample_users["employee1"]
        manager = sample_users["manager"]
        
        # Create tasks
        draft_task = Task(
            id=uuid.uuid4(),
            title="Draft Task",
            owner_user_id=employee.id,
            created_by_user_id=manager.id,
            state=TaskState.DRAFT
        )
        target_task = Task(
            id=uuid.uuid4(),
            title="Target Task",
            owner_user_id=employee.id,
            created_by_user_id=employee.id,
            state=TaskState.ACTIVE
        )
        db_session.add_all([draft_task, target_task])
        
        # Create merge proposal
        proposal = TaskMergeProposal(
            id=uuid.uuid4(),
            from_task_id=draft_task.id,
            to_task_id=target_task.id,
            proposed_by_user_id=employee.id,
            proposal_reason="Same task",
            status=MergeProposalStatus.PROPOSED
        )
        db_session.add(proposal)
        db_session.commit()
        
        # Cancel via API
        response = test_client.delete(
            f"/decisions/merge/{proposal.id}",
            headers={"X-User-Id": str(employee.id)}
        )
        
        assert response.status_code == 200


class TestMergeAcceptance:
    """Test merge acceptance flow."""
    
    def test_creator_accepts_merge(self, test_client, db_session, sample_users):
        """Original creator can accept merge proposal."""
        manager = sample_users["manager"]  # Created the draft
        employee = sample_users["employee1"]  # Proposed merge
        
        draft_task = Task(
            id=uuid.uuid4(),
            title="Suggested Task",
            owner_user_id=employee.id,
            created_by_user_id=manager.id,
            state=TaskState.DRAFT
        )
        target_task = Task(
            id=uuid.uuid4(),
            title="Existing Task",
            owner_user_id=employee.id,
            created_by_user_id=employee.id,
            state=TaskState.ACTIVE
        )
        db_session.add_all([draft_task, target_task])
        db_session.flush()
        
        proposal = TaskMergeProposal(
            id=uuid.uuid4(),
            from_task_id=draft_task.id,
            to_task_id=target_task.id,
            proposed_by_user_id=employee.id,
            proposal_reason="Same task",
            status=MergeProposalStatus.PROPOSED
        )
        db_session.add(proposal)
        db_session.commit()
        
        # Manager accepts
        response = test_client.post(
            f"/decisions/merge/{proposal.id}",
            json={"action": "accept"},
            headers={"X-User-Id": str(manager.id)}
        )
        
        assert response.status_code == 200
        
        db_session.refresh(proposal)
        assert proposal.status == MergeProposalStatus.ACCEPTED
    
    def test_merge_creates_alias(self, test_client, db_session, sample_users):
        """Accepted merge should create TaskAlias."""
        manager = sample_users["manager"]
        employee = sample_users["employee1"]
        
        draft_task = Task(
            id=uuid.uuid4(),
            title="Suggested Task",
            owner_user_id=employee.id,
            created_by_user_id=manager.id,
            state=TaskState.DRAFT
        )
        target_task = Task(
            id=uuid.uuid4(),
            title="Existing Task",
            owner_user_id=employee.id,
            created_by_user_id=employee.id,
            state=TaskState.ACTIVE
        )
        db_session.add_all([draft_task, target_task])
        db_session.flush()
        
        proposal = TaskMergeProposal(
            id=uuid.uuid4(),
            from_task_id=draft_task.id,
            to_task_id=target_task.id,
            proposed_by_user_id=employee.id,
            proposal_reason="Same task",
            status=MergeProposalStatus.PROPOSED
        )
        db_session.add(proposal)
        db_session.commit()
        
        # Accept merge
        response = test_client.post(
            f"/decisions/merge/{proposal.id}",
            json={"action": "accept"},
            headers={"X-User-Id": str(manager.id)}
        )
        
        assert response.status_code == 200
        
        # Check alias was created
        alias = db_session.query(TaskAlias).filter(
            TaskAlias.canonical_task_id == target_task.id,
            TaskAlias.alias_title == "Suggested Task"
        ).first()
        
        assert alias is not None
        assert alias.alias_created_by_user_id == manager.id
    
    def test_merge_archives_source_task(self, test_client, db_session, sample_users):
        """Merged-away task should be archived."""
        manager = sample_users["manager"]
        employee = sample_users["employee1"]
        
        draft_task = Task(
            id=uuid.uuid4(),
            title="Suggested Task",
            owner_user_id=employee.id,
            created_by_user_id=manager.id,
            state=TaskState.DRAFT
        )
        target_task = Task(
            id=uuid.uuid4(),
            title="Existing Task",
            owner_user_id=employee.id,
            created_by_user_id=employee.id,
            state=TaskState.ACTIVE
        )
        db_session.add_all([draft_task, target_task])
        db_session.flush()
        
        proposal = TaskMergeProposal(
            id=uuid.uuid4(),
            from_task_id=draft_task.id,
            to_task_id=target_task.id,
            proposed_by_user_id=employee.id,
            proposal_reason="Same task",
            status=MergeProposalStatus.PROPOSED
        )
        db_session.add(proposal)
        db_session.commit()
        
        response = test_client.post(
            f"/decisions/merge/{proposal.id}",
            json={"action": "accept"},
            headers={"X-User-Id": str(manager.id)}
        )
        
        assert response.status_code == 200
        
        db_session.refresh(draft_task)
        assert draft_task.state == TaskState.ARCHIVED


class TestMergeDataMigration:
    """Test that data is migrated during merge."""
    
    def test_attributes_migrated_to_canonical(self, test_client, db_session, sample_users, sample_attributes):
        """Attributes from merged task should appear on canonical."""
        manager = sample_users["manager"]
        employee = sample_users["employee1"]
        priority_attr = sample_attributes["priority"]
        
        draft_task = Task(
            id=uuid.uuid4(),
            title="Suggested Task",
            owner_user_id=employee.id,
            created_by_user_id=manager.id,
            state=TaskState.DRAFT
        )
        target_task = Task(
            id=uuid.uuid4(),
            title="Existing Task",
            owner_user_id=employee.id,
            created_by_user_id=employee.id,
            state=TaskState.ACTIVE
        )
        db_session.add_all([draft_task, target_task])
        db_session.flush()
        
        # Add answer to draft task
        answer = AttributeAnswer(
            id=uuid.uuid4(),
            answered_by_user_id=manager.id,
            target_user_id=employee.id,
            task_id=draft_task.id,
            attribute_id=priority_attr.id,
            value="High"
        )
        db_session.add(answer)
        
        proposal = TaskMergeProposal(
            id=uuid.uuid4(),
            from_task_id=draft_task.id,
            to_task_id=target_task.id,
            proposed_by_user_id=employee.id,
            proposal_reason="Same task",
            status=MergeProposalStatus.PROPOSED
        )
        db_session.add(proposal)
        db_session.commit()
        
        # Accept merge
        response = test_client.post(
            f"/decisions/merge/{proposal.id}",
            json={"action": "accept"},
            headers={"X-User-Id": str(manager.id)}
        )
        
        assert response.status_code == 200
        
        # Answer should now point to target task
        db_session.refresh(answer)
        assert answer.task_id == target_task.id
    
    def test_dependencies_migrated(self, test_client, db_session, sample_users, sample_tasks):
        """Dependencies should be migrated to canonical task."""
        manager = sample_users["manager"]
        employee = sample_users["employee1"]
        
        draft_task = Task(
            id=uuid.uuid4(),
            title="Suggested Task",
            owner_user_id=employee.id,
            created_by_user_id=manager.id,
            state=TaskState.DRAFT
        )
        target_task = Task(
            id=uuid.uuid4(),
            title="Existing Task",
            owner_user_id=employee.id,
            created_by_user_id=employee.id,
            state=TaskState.ACTIVE
        )
        other_task = sample_tasks["task2"]
        db_session.add_all([draft_task, target_task])
        db_session.flush()
        
        # Add dependency from draft task
        dep = TaskDependencyV2(
            id=uuid.uuid4(),
            downstream_task_id=draft_task.id,
            upstream_task_id=other_task.id,
            status=DependencyStatus.CONFIRMED,
            created_by_user_id=manager.id
        )
        db_session.add(dep)
        
        proposal = TaskMergeProposal(
            id=uuid.uuid4(),
            from_task_id=draft_task.id,
            to_task_id=target_task.id,
            proposed_by_user_id=employee.id,
            proposal_reason="Same task",
            status=MergeProposalStatus.PROPOSED
        )
        db_session.add(proposal)
        db_session.commit()
        
        # Accept merge
        response = test_client.post(
            f"/decisions/merge/{proposal.id}",
            json={"action": "accept"},
            headers={"X-User-Id": str(manager.id)}
        )
        
        assert response.status_code == 200
        
        # Dependency should point to target task
        db_session.refresh(dep)
        assert dep.downstream_task_id == target_task.id


class TestMergeRejection:
    """Test merge rejection flow."""
    
    def test_creator_rejects_merge(self, test_client, db_session, sample_users):
        """Original creator can reject merge proposal."""
        manager = sample_users["manager"]
        employee = sample_users["employee1"]
        
        draft_task = Task(
            id=uuid.uuid4(),
            title="Suggested Task",
            owner_user_id=employee.id,
            created_by_user_id=manager.id,
            state=TaskState.DRAFT
        )
        target_task = Task(
            id=uuid.uuid4(),
            title="Existing Task",
            owner_user_id=employee.id,
            created_by_user_id=employee.id,
            state=TaskState.ACTIVE
        )
        db_session.add_all([draft_task, target_task])
        db_session.flush()
        
        proposal = TaskMergeProposal(
            id=uuid.uuid4(),
            from_task_id=draft_task.id,
            to_task_id=target_task.id,
            proposed_by_user_id=employee.id,
            proposal_reason="Same task",
            status=MergeProposalStatus.PROPOSED
        )
        db_session.add(proposal)
        db_session.commit()
        
        # Manager rejects
        response = test_client.post(
            f"/decisions/merge/{proposal.id}",
            json={"action": "reject", "reason": "These are different tasks"},
            headers={"X-User-Id": str(manager.id)}
        )
        
        assert response.status_code == 200
        
        db_session.refresh(proposal)
        assert proposal.status == MergeProposalStatus.REJECTED
        assert proposal.rejected_reason == "These are different tasks"
    
    def test_rejected_merge_keeps_task_draft(self, test_client, db_session, sample_users):
        """Rejected merge should keep task in DRAFT state."""
        manager = sample_users["manager"]
        employee = sample_users["employee1"]
        
        draft_task = Task(
            id=uuid.uuid4(),
            title="Suggested Task",
            owner_user_id=employee.id,
            created_by_user_id=manager.id,
            state=TaskState.DRAFT
        )
        target_task = Task(
            id=uuid.uuid4(),
            title="Existing Task",
            owner_user_id=employee.id,
            created_by_user_id=employee.id,
            state=TaskState.ACTIVE
        )
        db_session.add_all([draft_task, target_task])
        db_session.flush()
        
        proposal = TaskMergeProposal(
            id=uuid.uuid4(),
            from_task_id=draft_task.id,
            to_task_id=target_task.id,
            proposed_by_user_id=employee.id,
            proposal_reason="Same task",
            status=MergeProposalStatus.PROPOSED
        )
        db_session.add(proposal)
        db_session.commit()
        
        response = test_client.post(
            f"/decisions/merge/{proposal.id}",
            json={"action": "reject", "reason": "Different tasks"},
            headers={"X-User-Id": str(manager.id)}
        )
        
        assert response.status_code == 200
        
        db_session.refresh(draft_task)
        assert draft_task.state == TaskState.DRAFT  # Still draft, not archived

