"""Simple migration runner: executes SQL files in backend/migrations in filename order.
Usage: python run_migrations.py
It reads Config.DATABASE_URL and runs each .sql file in the migrations directory.
"""
import os
import glob
import psycopg2
from config import Config
import logging

logger = logging.getLogger(__name__)

def run():
    migrations_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'migrations')
    files = sorted(glob.glob(os.path.join(migrations_dir, '*.sql')))
    if not files:
        print('No migration files found in', migrations_dir)
        return

    conn = psycopg2.connect(Config.DATABASE_URL)
    try:
        with conn:
            with conn.cursor() as cur:
                for f in files:
                    print('Applying', f)
                    with open(f, 'r', encoding='utf-8') as fh:
                        sql = fh.read()
                        cur.execute(sql)
        print('Migrations applied successfully')
    except Exception as e:
        print('Migration failed:', e)
    finally:
        conn.close()

if __name__ == '__main__':
    run()
