import sqlite3
import os
import psycopg2
from psycopg2.extras import RealDictCursor
from urllib.parse import urlparse

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE = os.path.join(BASE_DIR, 'database.db')
DATABASE_URL = os.environ.get('DATABASE_URL')

if DATABASE_URL:
    import psycopg2
    from psycopg2 import OperationalError, IntegrityError
    from psycopg2.extras import RealDictCursor
else:
    import sqlite3
    from sqlite3 import OperationalError, IntegrityError

def get_db():
    if DATABASE_URL:
        # PostgreSQL (Supabase)
        conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
        # Patch connection to behave like SQLite's connection for simple use cases
        def execute_wrapper(query, params=None):
            # Convert SQLite placeholders (?) to PostgreSQL (%s)
            query = query.replace('?', '%s')
            # Convert INSERT OR IGNORE to PostgreSQL ON CONFLICT DO NOTHING
            if 'INSERT OR IGNORE' in query.upper():
                query = query.upper().replace('INSERT OR IGNORE', 'INSERT')
                if 'ON CONFLICT' not in query:
                    query += ' ON CONFLICT DO NOTHING'
            
            cur = conn.cursor()
            try:
                cur.execute(query, params or ())
                return cur
            except Exception as e:
                conn.rollback()
                raise e
        
        conn.execute = execute_wrapper
        return conn
    else:
        # SQLite (Local)
        conn = sqlite3.connect(DATABASE)
        conn.row_factory = sqlite3.Row
        return conn

def init_db():
    conn = get_db()
    with open('schema.sql', 'r', encoding='utf-8') as f:
        sql = f.read()
        if DATABASE_URL:
            # PostgreSQL não aceita executescript diretamente do sqlite3
            with conn.cursor() as cur:
                cur.execute(sql)
            conn.commit()
        else:
            conn.executescript(sql)
            conn.commit()
    conn.close()

if __name__ == "__main__":
    init_db()
    print("Database initialized successfully!")
