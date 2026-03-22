import sqlite3

def migrate():
    conn = sqlite3.connect('database.db')
    try:
        conn.execute('ALTER TABLE messages ADD COLUMN file_path TEXT')
        print("Adicionada coluna file_path")
    except sqlite3.OperationalError:
        print("file_path já existe")
        
    try:
        conn.execute('ALTER TABLE messages ADD COLUMN reply_to_id INTEGER')
        print("Adicionada coluna reply_to_id")
    except sqlite3.OperationalError:
        print("reply_to_id já existe")
        
    conn.commit()
    conn.close()

if __name__ == "__main__":
    migrate()
