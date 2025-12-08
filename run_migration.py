"""Run database migration"""
import sys
from sqlalchemy import text
from app.database import engine

def run_migration(sql_file):
    with open(sql_file, 'r') as f:
        sql = f.read()
    
    with engine.connect() as conn:
        # Execute each statement separately
        for statement in sql.split(';'):
            statement = statement.strip()
            if statement and not statement.startswith('--') and not statement.startswith('COMMENT'):
                print(f"Executing: {statement[:100]}...")
                conn.execute(text(statement))
                conn.commit()
    
    print(f"✅ Migration complete: {sql_file}")

if __name__ == "__main__":
    run_migration("migrations/add_similarity_scores_table.sql")

