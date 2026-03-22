import sqlite3

def migrate():
    conn = sqlite3.connect('database.db')
    try:
        conn.execute("ALTER TABLE topics ADD COLUMN status TEXT DEFAULT 'aguardando'")
        print("Adicionada coluna status")
    except sqlite3.OperationalError:
        print("status já existe")
    conn.commit()
    conn.close()

if __name__ == "__main__":
    migrate()
