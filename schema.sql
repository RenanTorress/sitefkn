CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    name TEXT,
    role TEXT DEFAULT 'admin',
    profile_pic TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS folders (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    parent_id INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(parent_id) REFERENCES folders(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS files (
    id SERIAL PRIMARY KEY,
    filename TEXT NOT NULL,
    filepath TEXT NOT NULL,
    size BIGINT NOT NULL,
    folder_id INTEGER,
    uploaded_by INTEGER,
    uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    download_count INTEGER DEFAULT 0,
    FOREIGN KEY(folder_id) REFERENCES folders(id) ON DELETE CASCADE,
    FOREIGN KEY(uploaded_by) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS forums (
    id SERIAL PRIMARY KEY,
    title TEXT NOT NULL,
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS topics (
    id SERIAL PRIMARY KEY,
    forum_id INTEGER NOT NULL,
    title TEXT NOT NULL,
    author_name TEXT NOT NULL,
    status TEXT DEFAULT 'aguardando',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(forum_id) REFERENCES forums(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS messages (
    id SERIAL PRIMARY KEY,
    topic_id INTEGER NOT NULL,
    author_name TEXT NOT NULL,
    content TEXT NOT NULL,
    is_admin BOOLEAN DEFAULT FALSE,
    file_path TEXT,
    reply_to_id INTEGER,
    user_id INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(topic_id) REFERENCES topics(id) ON DELETE CASCADE,
    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS bug_reports (
    id SERIAL PRIMARY KEY,
    message TEXT NOT NULL,
    attachment_path TEXT,
    is_resolved BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS exams (
    id SERIAL PRIMARY KEY,
    title TEXT NOT NULL,
    folder_id INTEGER,
    pdf_path TEXT,
    start_at TIMESTAMP,
    end_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(folder_id) REFERENCES folders(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS exam_questions (
    id SERIAL PRIMARY KEY,
    exam_id INTEGER NOT NULL,
    question_image TEXT,
    resolution_image TEXT,
    resolution_text TEXT,
    correct_option CHAR(1),
    FOREIGN KEY(exam_id) REFERENCES exams(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS faqs (
    id SERIAL PRIMARY KEY,
    question TEXT NOT NULL,
    answer TEXT NOT NULL,
    keyword TEXT,
    redirect_url TEXT,
    order_num INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS logs (
    id SERIAL PRIMARY KEY,
    user_id INTEGER,
    action TEXT NOT NULL,
    details TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS exam_submissions (
    id SERIAL PRIMARY KEY,
    exam_id INTEGER NOT NULL,
    student_name TEXT NOT NULL,
    score INTEGER NOT NULL,
    total_questions INTEGER NOT NULL,
    percentage REAL NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(exam_id) REFERENCES exams(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS submission_details (
    id SERIAL PRIMARY KEY,
    submission_id INTEGER NOT NULL,
    question_id INTEGER NOT NULL,
    is_correct BOOLEAN NOT NULL,
    user_choice CHAR(1),
    FOREIGN KEY(submission_id) REFERENCES exam_submissions(id) ON DELETE CASCADE,
    FOREIGN KEY(question_id) REFERENCES exam_questions(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS daily_access (
    access_date DATE PRIMARY KEY,
    count INTEGER DEFAULT 0
);

-- Dados base usando sintaxe PostgreSQL
INSERT INTO settings (key, value) VALUES ('site_name', 'Física com FKN') ON CONFLICT (key) DO NOTHING;
INSERT INTO settings (key, value) VALUES ('primary_color', '#3b82f6') ON CONFLICT (key) DO NOTHING;
INSERT INTO settings (key, value) VALUES ('home_announcement', 'Bem-vindos à nova plataforma de estudos!') ON CONFLICT (key) DO NOTHING;
INSERT INTO settings (key, value) VALUES ('home_about', 'Este espaço é dedicado ao seu aprendizado.') ON CONFLICT (key) DO NOTHING;
INSERT INTO settings (key, value) VALUES ('dev_instagram_url', 'https://www.instagram.com/renantorres.dev/') ON CONFLICT (key) DO NOTHING;
INSERT INTO settings (key, value) VALUES ('dev_name', 'Renan Torres') ON CONFLICT (key) DO NOTHING;
INSERT INTO settings (key, value) VALUES ('show_dev_name', '1') ON CONFLICT (key) DO NOTHING;
INSERT INTO settings (key, value) VALUES ('x_url', '') ON CONFLICT (key) DO NOTHING;
INSERT INTO settings (key, value) VALUES ('facebook_url', '') ON CONFLICT (key) DO NOTHING;
INSERT INTO settings (key, value) VALUES ('whatsapp_url', '') ON CONFLICT (key) DO NOTHING;
INSERT INTO settings (key, value) VALUES ('footer_rights', 'Física com FKN - Todos os direitos reservados.') ON CONFLICT (key) DO NOTHING;

-- Base FAQ
INSERT INTO faqs (question, answer, keyword, redirect_url) VALUES ('Onde acesso os materiais?', 'Você pode acessar todos os materiais e PDFs na nossa área exclusiva de materiais.', 'materiais', '/materiais') ON CONFLICT (id) DO NOTHING;
INSERT INTO faqs (question, answer, keyword, redirect_url) VALUES ('Como vejo minha turma?', 'Sua turma é definida pelo seu cronograma de estudos no painel principal.', 'fórum', '/forum') ON CONFLICT (id) DO NOTHING;
INSERT INTO faqs (question, answer, keyword, redirect_url) VALUES ('Onde tiro as dúvidas?', 'Temos uma central de Helpdesk pronta para te ouvir em tempo real através dos fóruns de cada matéria.', 'Helpdesk', '/forum') ON CONFLICT (id) DO NOTHING;
