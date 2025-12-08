"""
Populate similarity scores for all existing answers in the database.

Run this once after deploying the caching system to pre-calculate
all similarity scores for existing data.
"""
import asyncio
import logging
from app.database import get_db
from app.services.similarity_cache import recalculate_all_scores

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def main():
    """Populate all similarity scores"""
    logger.info("="*70)
    logger.info("POPULATING SIMILARITY SCORES")
    logger.info("="*70)
    
    db = next(get_db())
    
    try:
        total_scores = await recalculate_all_scores(db)
        
        logger.info("="*70)
        logger.info(f"✅ SUCCESS! Calculated {total_scores} similarity scores")
        logger.info("="*70)
        
    except Exception as e:
        logger.error(f"❌ Error populating scores: {e}", exc_info=True)
        raise
    finally:
        db.close()


if __name__ == "__main__":
    asyncio.run(main())

