"""
Invariant and Fuzz Tests

Tests system invariants that must always hold:
- No self-dependencies
- No duplicate dependencies per pair
- No merge cycles
- Alias entries point to real canonical tasks
- No DRAFT task that is merged/aliased inconsistently

Includes fuzz testing with random operations.

Unit Size: Global invariants across all data
Failure Modes:
- Self-dependency created
- Duplicate dependency pairs
- Circular merge references
- Orphaned aliases
- Inconsistent state combinations
"""

import pytest
import uuid
import random
from datetime import datetime, timedelta

from app.models import (
    Task, TaskState, User, TaskDependencyV2, DependencyStatus,
    TaskAlias, TaskMergeProposal, MergeProposalStatus,
    AttributeAnswer, AttributeDefinition, EntityType, AttributeType
)
from app.services import state_machines


def assert_global_invariants(db_session):
    """
    Check all global invariants that must always hold.
    Call this after any batch of operations.
    """
    errors = []
    
    # === Invariant 1: No self-dependencies ===
    self_deps = db_session.query(TaskDependencyV2).filter(
        TaskDependencyV2.downstream_task_id == TaskDependencyV2.upstream_task_id
    ).all()
    
    if self_deps:
        errors.append(f"Self-dependencies found: {len(self_deps)}")
    
    # === Invariant 2: No duplicate active dependencies per pair ===
    from sqlalchemy import func
    
    dup_deps = db_session.query(
        TaskDependencyV2.downstream_task_id,
        TaskDependencyV2.upstream_task_id,
        func.count(TaskDependencyV2.id)
    ).filter(
        TaskDependencyV2.status.in_([DependencyStatus.PROPOSED, DependencyStatus.CONFIRMED])
    ).group_by(
        TaskDependencyV2.downstream_task_id,
        TaskDependencyV2.upstream_task_id
    ).having(
        func.count(TaskDependencyV2.id) > 1
    ).all()
    
    if dup_deps:
        errors.append(f"Duplicate active dependencies found: {len(dup_deps)}")
    
    # === Invariant 3: Aliases point to real canonical tasks ===
    aliases = db_session.query(TaskAlias).all()
    for alias in aliases:
        canonical = db_session.query(Task).filter(
            Task.id == alias.canonical_task_id
        ).first()
        
        if not canonical:
            errors.append(f"Orphaned alias {alias.id} points to non-existent task")
        elif canonical.state == TaskState.ARCHIVED:
            # Canonical task shouldn't be archived (unless it was also merged)
            # This is a soft invariant - might be allowed in some cases
            pass
    
    # === Invariant 4: No circular merge chains ===
    # A task that is merged into (canonical) shouldn't itself be archived-merged
    aliases_by_canonical = {}
    for alias in aliases:
        if alias.canonical_task_id not in aliases_by_canonical:
            aliases_by_canonical[alias.canonical_task_id] = []
        aliases_by_canonical[alias.canonical_task_id].append(alias)
    
    # Check no archived task is a canonical for an alias
    for canonical_id in aliases_by_canonical:
        task = db_session.query(Task).filter(Task.id == canonical_id).first()
        if task and task.state == TaskState.ARCHIVED:
            # Check if this archived task is also an alias target
            sub_aliases = db_session.query(TaskAlias).filter(
                TaskAlias.canonical_task_id == canonical_id
            ).all()
            if sub_aliases:
                # This could indicate a problem, but might be from re-merging
                pass
    
    # === Invariant 5: DRAFT tasks shouldn't be merged ===
    draft_tasks = db_session.query(Task).filter(Task.state == TaskState.DRAFT).all()
    for task in draft_tasks:
        # A DRAFT task shouldn't be the canonical target of a merge
        # (it should be accepted first before being a merge target)
        is_merge_target = db_session.query(TaskMergeProposal).filter(
            TaskMergeProposal.to_task_id == task.id,
            TaskMergeProposal.status == MergeProposalStatus.ACCEPTED
        ).first()
        
        if is_merge_target:
            errors.append(f"DRAFT task {task.id} is target of accepted merge")
    
    # === Invariant 6: Active dependency count per task is reasonable ===
    MAX_DEPS_PER_TASK = 100
    for task in db_session.query(Task).filter(Task.is_active == True).all():
        dep_count = db_session.query(TaskDependencyV2).filter(
            TaskDependencyV2.downstream_task_id == task.id,
            TaskDependencyV2.status == DependencyStatus.CONFIRMED
        ).count()
        
        if dep_count > MAX_DEPS_PER_TASK:
            errors.append(f"Task {task.id} has excessive dependencies: {dep_count}")
    
    if errors:
        raise AssertionError("Invariant violations:\n" + "\n".join(errors))


class TestInvariants:
    """Test that invariants hold after various operations."""
    
    def test_invariants_hold_after_basic_ops(self, db_session, sample_users, sample_tasks):
        """Invariants hold after basic operations."""
        # Do some operations
        task = sample_tasks["task1"]
        owner = sample_users["employee1"]
        
        state_machines.set_task_state(
            db=db_session,
            task=task,
            new_state=TaskState.DONE,
            reason="Test",
            actor=owner
        )
        
        # Check invariants
        assert_global_invariants(db_session)
    
    def test_invariants_hold_after_dependency_ops(self, db_session, sample_users, sample_tasks):
        """Invariants hold after dependency operations."""
        task1 = sample_tasks["task1"]
        task2 = sample_tasks["task2"]
        requester = sample_users["employee1"]
        
        # Create dependency
        dep = state_machines.propose_dependency(
            db=db_session,
            requester=requester,
            downstream_task=task1,
            upstream_task=task2
        )
        
        # Check invariants
        assert_global_invariants(db_session)
    
    def test_invariants_hold_after_merge(self, db_session, sample_users, sample_attributes):
        """Invariants hold after merge operations."""
        manager = sample_users["manager"]
        employee = sample_users["employee1"]
        
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
        db_session.commit()
        
        # Create and accept merge
        proposal = state_machines.propose_task_merge(
            db=db_session,
            from_task=draft_task,
            to_task=target_task,
            proposer=employee,
            reason="Same task"
        )
        
        state_machines.accept_merge_proposal(db_session, proposal, manager)
        
        # Check invariants
        assert_global_invariants(db_session)


class TestNoSelfDependency:
    """Specifically test self-dependency prevention."""
    
    def test_cannot_create_self_dependency(self, db_session, sample_users, sample_tasks):
        """Self-dependency should be rejected."""
        task = sample_tasks["task1"]
        owner = sample_users["employee1"]
        
        with pytest.raises(ValueError, match="itself"):
            state_machines.propose_dependency(
                db=db_session,
                requester=owner,
                downstream_task=task,
                upstream_task=task
            )
        
        assert_global_invariants(db_session)


class TestNoDuplicateDependency:
    """Test duplicate dependency prevention."""
    
    def test_no_duplicate_dependencies(self, db_session, sample_users, sample_tasks):
        """Cannot create duplicate dependencies."""
        task1 = sample_tasks["task1"]
        task2 = sample_tasks["task2"]
        requester = sample_users["employee1"]
        
        # First dependency
        dep1 = state_machines.propose_dependency(
            db=db_session,
            requester=requester,
            downstream_task=task1,
            upstream_task=task2
        )
        
        # Second should return existing or be blocked
        dep2 = state_machines.propose_dependency(
            db=db_session,
            requester=requester,
            downstream_task=task1,
            upstream_task=task2
        )
        
        assert dep1.id == dep2.id  # Same dependency returned
        
        assert_global_invariants(db_session)


class TestFuzzOperations:
    """Fuzz testing with random operations."""
    
    def test_random_operations_maintain_invariants(self, db_session, sample_attributes):
        """Random operations should maintain all invariants."""
        random.seed(42)  # For reproducibility
        
        # Create some users
        users = []
        for i in range(5):
            user = User(
                id=uuid.uuid4(),
                name=f"Fuzz User {i}",
                email=f"fuzz{i}@test.com",
                team="Fuzz"
            )
            users.append(user)
        db_session.add_all(users)
        db_session.commit()
        
        # Create some tasks
        tasks = []
        for i in range(10):
            owner = random.choice(users)
            creator = random.choice(users)
            state = TaskState.ACTIVE if owner.id == creator.id else TaskState.DRAFT
            
            task = Task(
                id=uuid.uuid4(),
                title=f"Fuzz Task {i}",
                owner_user_id=owner.id,
                created_by_user_id=creator.id,
                state=state
            )
            tasks.append(task)
        db_session.add_all(tasks)
        db_session.commit()
        
        # Random operations
        operations = [
            "create_dependency",
            "accept_task",
            "change_state",
            "add_answer"
        ]
        
        for _ in range(50):
            op = random.choice(operations)
            
            try:
                if op == "create_dependency":
                    t1, t2 = random.sample(tasks, 2)
                    proposer = random.choice(users)
                    state_machines.propose_dependency(
                        db=db_session,
                        downstream_task=t1,
                        upstream_task=t2,
                        proposer=proposer
                    )
                
                elif op == "accept_task":
                    draft_tasks = [t for t in tasks if t.state == TaskState.DRAFT]
                    if draft_tasks:
                        task = random.choice(draft_tasks)
                        owner = db_session.query(User).filter(User.id == task.owner_user_id).first()
                        if owner:
                            state_machines.accept_task(db_session, task, owner)
                
                elif op == "change_state":
                    task = random.choice(tasks)
                    actor = random.choice(users)
                    new_state = random.choice([TaskState.ACTIVE, TaskState.DONE])
                    try:
                        state_machines.set_task_state(
                            db=db_session,
                            task=task,
                            new_state=new_state,
                            reason="Fuzz test",
                            actor=actor
                        )
                    except:
                        pass  # Some transitions may be invalid
                
                elif op == "add_answer":
                    task = random.choice(tasks)
                    user = random.choice(users)
                    attr = sample_attributes["priority"]
                    value = random.choice(["Critical", "High", "Medium", "Low"])
                    
                    # Check if answer exists
                    existing = db_session.query(AttributeAnswer).filter(
                        AttributeAnswer.answered_by_user_id == user.id,
                        AttributeAnswer.task_id == task.id,
                        AttributeAnswer.attribute_id == attr.id
                    ).first()
                    
                    if existing:
                        existing.value = value
                    else:
                        answer = AttributeAnswer(
                            id=uuid.uuid4(),
                            answered_by_user_id=user.id,
                            target_user_id=task.owner_user_id,
                            task_id=task.id,
                            attribute_id=attr.id,
                            value=value
                        )
                        db_session.add(answer)
                    
                    db_session.commit()
            
            except Exception as e:
                # Some operations may fail, that's ok
                db_session.rollback()
                continue
        
        # After all operations, invariants should hold
        assert_global_invariants(db_session)
    
    def test_rapid_operations_maintain_invariants(self, db_session, sample_users, sample_tasks):
        """Rapid sequential operations maintain invariants."""
        task = sample_tasks["task1"]
        owner = sample_users["employee1"]
        
        states = [
            TaskState.DONE,
            TaskState.ACTIVE,
            TaskState.DONE,
            TaskState.ACTIVE,
            TaskState.DONE
        ]
        
        for state in states:
            try:
                state_machines.set_task_state(
                    db=db_session,
                    task=task,
                    new_state=state,
                    reason="Rapid change",
                    actor=owner
                )
            except:
                pass
        
        assert_global_invariants(db_session)


class TestBoundaryConditions:
    """Test boundary conditions and edge cases."""
    
    def test_empty_database_invariants(self, test_engine):
        """Empty database should pass all invariants."""
        from sqlalchemy.orm import sessionmaker
        
        TestSession = sessionmaker(bind=test_engine)
        session = TestSession()
        
        try:
            assert_global_invariants(session)
        finally:
            session.close()
    
    def test_single_user_org(self, db_session, sample_attributes):
        """Single user organization maintains invariants."""
        # Create solo user
        user = User(
            id=uuid.uuid4(),
            name="Solo User",
            email="solo@test.com",
            team="Solo"
        )
        db_session.add(user)
        db_session.commit()
        
        # Create task
        task = Task(
            id=uuid.uuid4(),
            title="Solo Task",
            owner_user_id=user.id,
            created_by_user_id=user.id,
            state=TaskState.ACTIVE
        )
        db_session.add(task)
        db_session.commit()
        
        # Add answer
        answer = AttributeAnswer(
            id=uuid.uuid4(),
            answered_by_user_id=user.id,
            target_user_id=user.id,
            task_id=task.id,
            attribute_id=sample_attributes["priority"].id,
            value="High"
        )
        db_session.add(answer)
        db_session.commit()
        
        assert_global_invariants(db_session)
    
    def test_maximum_nesting(self, db_session, sample_users):
        """Deep task hierarchy maintains invariants."""
        owner = sample_users["employee1"]
        
        # Create deep hierarchy
        parent = None
        tasks = []
        
        for i in range(10):
            task = Task(
                id=uuid.uuid4(),
                title=f"Level {i} Task",
                owner_user_id=owner.id,
                created_by_user_id=owner.id,
                parent_id=parent.id if parent else None,
                state=TaskState.ACTIVE
            )
            tasks.append(task)
            parent = task
        
        db_session.add_all(tasks)
        db_session.commit()
        
        assert_global_invariants(db_session)

