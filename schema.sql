CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role TEXT DEFAULT 'admin',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS folders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    parent_id INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(parent_id) REFERENCES folders(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    filename TEXT NOT NULL,
    filepath TEXT NOT NULL,
    size INTEGER NOT NULL,
    folder_id INTEGER,
    uploaded_by INTEGER,
    uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(folder_id) REFERENCES folders(id) ON DELETE CASCADE,
    FOREIGN KEY(uploaded_by) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS forums (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS topics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    forum_id INTEGER NOT NULL,
    title TEXT NOT NULL,
    author_name TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(forum_id) REFERENCES forums(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    topic_id INTEGER NOT NULL,
    author_name TEXT NOT NULL,
    content TEXT NOT NULL,
    is_admin BOOLEAN DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(topic_id) REFERENCES topics(id) ON DELETE CASCADE
);

-- Dados base
INSERT OR IGNORE INTO settings (key, value) VALUES ('site_name', 'Física com FKN');
INSERT OR IGNORE INTO settings (key, value) VALUES ('primary_color', '#3b82f6');
INSERT OR IGNORE INTO settings (key, value) VALUES ('home_announcement', 'Bem-vindos à nova plataforma de estudos! Fiquem de olho nos novos materiais adicionados e tirem suas dúvidas no fórum.');
INSERT OR IGNORE INTO settings (key, value) VALUES ('home_about', 'Este espaço é dedicado ao seu aprendizado. Acesse diariamente a área de materiais para fazer o download do currículo da disciplina, listas de exercícios e guias práticos.');
