import sqlite3

def migrate():
    conn = sqlite3.connect('database.db')
    commands = [
        "ALTER TABLE users ADD COLUMN name TEXT",
        "ALTER TABLE users ADD COLUMN profile_pic TEXT",
        "ALTER TABLE messages ADD COLUMN user_id INTEGER"
    ]
    for cmd in commands:
        try:
            conn.execute(cmd)
            print("Successfully executed:", cmd)
        except sqlite3.OperationalError:
            print("Skipped (already exists):", cmd)
            
    # Set default names for existing users
    conn.execute("UPDATE users SET name = 'Mestre Admin' WHERE email = 'admin@admin.com' AND name IS NULL")
    conn.execute("UPDATE users SET name = 'Professor' WHERE name IS NULL")
    
    conn.commit()
    conn.close()

if __name__ == "__main__":
    migrate()
