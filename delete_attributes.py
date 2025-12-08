#!/usr/bin/env python3
"""
Delete specific attributes and all their associated data
"""
import sys
sys.path.insert(0, '/Users/ishaylevi/work/OrgOs')

from app.database import SessionLocal
from app.models import AttributeDefinition, AttributeAnswer, SimilarityScore, QuestionLog

# Attributes to delete
ATTRIBUTES_TO_DELETE = [
    "value_type",
    "is_blocked",
    "blocking_reason",
    "impact_size",
    "direction_confidence",
    "perceived_dependencies"
]

def delete_attributes():
    """Delete specified attributes and their data"""
    print("\n" + "="*70)
    print("🗑️  DELETING SPECIFIED ATTRIBUTES")
    print("="*70)
    
    db = SessionLocal()
    
    try:
        for attr_name in ATTRIBUTES_TO_DELETE:
            print(f"\n📋 Processing: {attr_name}")
            
            # Find the attribute
            attr = db.query(AttributeDefinition).filter(
                AttributeDefinition.name == attr_name
            ).first()
            
            if not attr:
                print(f"   ⚠️  Not found: {attr_name}")
                continue
            
            # Count related data
            answers = db.query(AttributeAnswer).filter(
                AttributeAnswer.attribute_id == attr.id
            ).count()
            
            similarity_scores = db.query(SimilarityScore).join(
                AttributeAnswer, 
                (SimilarityScore.answer_a_id == AttributeAnswer.id) | 
                (SimilarityScore.answer_b_id == AttributeAnswer.id)
            ).filter(
                AttributeAnswer.attribute_id == attr.id
            ).count()
            
            # Count question logs
            question_logs = db.query(QuestionLog).filter(
                QuestionLog.attribute_id == attr.id
            ).count()
            
            print(f"   Found: {answers} answers, ~{similarity_scores} similarity scores, {question_logs} question logs")
            
            # Delete question logs first
            db.query(QuestionLog).filter(
                QuestionLog.attribute_id == attr.id
            ).delete()
            
            # Delete similarity scores
            db.query(SimilarityScore).filter(
                SimilarityScore.answer_a_id.in_(
                    db.query(AttributeAnswer.id).filter(
                        AttributeAnswer.attribute_id == attr.id
                    )
                )
            ).delete(synchronize_session=False)
            
            db.query(SimilarityScore).filter(
                SimilarityScore.answer_b_id.in_(
                    db.query(AttributeAnswer.id).filter(
                        AttributeAnswer.attribute_id == attr.id
                    )
                )
            ).delete(synchronize_session=False)
            
            # Delete answers
            db.query(AttributeAnswer).filter(
                AttributeAnswer.attribute_id == attr.id
            ).delete()
            
            # Delete attribute definition
            db.delete(attr)
            
            print(f"   ✅ Deleted {attr_name}")
        
        db.commit()
        
        # Show remaining attributes
        print("\n" + "="*70)
        print("✅ DELETION COMPLETE")
        print("="*70)
        
        remaining = db.query(AttributeDefinition).filter(
            AttributeDefinition.entity_type == 'task'
        ).all()
        
        print(f"\n📊 Remaining task attributes ({len(remaining)}):")
        for attr in remaining:
            answer_count = db.query(AttributeAnswer).filter(
                AttributeAnswer.attribute_id == attr.id
            ).count()
            print(f"   • {attr.name:20} ({attr.type}) - {answer_count} answers")
        
        print("\n" + "="*70)
        print("🎯 NEXT STEPS:")
        print("="*70)
        print("1. Recalculate similarity scores:")
        print("   python3 populate_similarity_scores.py")
        print("\n2. Hard refresh browser (Cmd+Shift+R)")
        print()
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        db.rollback()
    finally:
        db.close()


if __name__ == "__main__":
    delete_attributes()

