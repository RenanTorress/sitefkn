import sqlite3
import os
import pg8000.dbapi
from urllib.parse import urlparse, unquote

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE = os.path.join(BASE_DIR, 'database.db')
DATABASE_URL = os.environ.get('DATABASE_URL')

if DATABASE_URL:
    from pg8000.dbapi import OperationalError, IntegrityError
else:
    from sqlite3 import OperationalError, IntegrityError

def get_db():
    if DATABASE_URL:
        # PostgreSQL (Supabase) via pg8000 (Pure Python)
        url = urlparse(DATABASE_URL)
        conn = pg8000.dbapi.connect(
            user=unquote(url.username) if url.username else None,
            password=unquote(url.password) if url.password else None,
            host=url.hostname,
            port=url.port or 5432,
            database=url.path[1:] if url.path else 'postgres'
        )

        # Patch connection to behave like SQLite's connection and return dict-like rows
        def execute_wrapper(query, params=None):
            query = query.replace('?', '%s')
            if 'INSERT OR IGNORE' in query.upper():
                query = query.upper().replace('INSERT OR IGNORE', 'INSERT')
                if 'ON CONFLICT' not in query:
                    query += ' ON CONFLICT DO NOTHING'

            cur = conn.cursor()
            try:
                cur.execute(query, params or ())
                # Suporte a acesso por nome de coluna (dict-like)
                if cur.description:
                    columns = [col[0] for col in cur.description]
                    original_fetchall = cur.fetchall
                    cur.fetchall = lambda: [dict(zip(columns, row)) for row in original_fetchall()]
                    original_fetchone = cur.fetchone
                    cur.fetchone = lambda: dict(zip(columns, row)) if (row := original_fetchone()) else None
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
            # PostgreSQL: executa cada statement individualmente para evitar timeout
            statements = [s.strip() for s in sql.split(';') if s.strip()]
            for stmt in statements:
                try:
                    conn.execute(stmt)
                    conn.commit()
                except Exception as e:
                    print(f"[init_db] Aviso: {e}")
        else:
            conn.executescript(sql)
            conn.commit()
    conn.close()

if __name__ == "__main__":
    init_db()
    print("Database initialized successfully!")
