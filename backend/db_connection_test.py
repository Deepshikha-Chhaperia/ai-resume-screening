import os
import sys
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv('CLOUD_SQL_DATABASE_URL') or os.getenv('DATABASE_URL')
print(f"Effective DATABASE_URL: {DATABASE_URL}")

try:
    import psycopg2
except Exception as e:
    print("psycopg2 not installed or import failed:", e)
    print("Install with: pip install psycopg2-binary")
    sys.exit(2)

if not DATABASE_URL:
    print("No DATABASE_URL found in environment. Check your .env or set CLOUD_SQL_DATABASE_URL/DATABASE_URL.")
    sys.exit(3)

try:
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    cur.execute('SELECT current_database(), version();')
    row = cur.fetchone()
    print('Connected to database:', row[0])
    print('Server version:', row[1])
    cur.close()
    conn.close()
    sys.exit(0)
except Exception as e:
    print('Connection failed:', e)
    print('\nTroubleshooting tips:')
    print('- If this is a Cloud SQL instance, use Cloud SQL Auth Proxy or set CLOUD_SQL_DATABASE_URL.')
    print('- Ensure the database host is reachable from this machine (Test-NetConnection on Windows).')
    print('- Check firewall, VPC, or authorized networks.')
    sys.exit(1)
