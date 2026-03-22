from flask import Flask, render_template, request, redirect, url_for, session, send_from_directory, flash, g
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import os
import sqlite3, time, datetime
from database import get_db, init_db

app = Flask(__name__)
app.secret_key = 'super_secret_key_change_in_production'

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'static', 'uploads')
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(os.path.join(UPLOAD_FOLDER, 'forum'), exist_ok=True)
os.makedirs(os.path.join(UPLOAD_FOLDER, 'avatars'), exist_ok=True)
os.makedirs(os.path.join(BASE_DIR, 'static', 'images'), exist_ok=True)

ALLOWED_EXTENSIONS = {'pdf', 'png', 'jpg', 'jpeg', 'gif', 'doc', 'docx', 'zip'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def format_size(size_in_bytes):
    if size_in_bytes is None: return "0 B"
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size_in_bytes < 1024.0: return f"{size_in_bytes:.1f} {unit}"
        size_in_bytes /= 1024.0

app.jinja_env.filters['format_size'] = format_size

def log_action(user_id, action, details=None):
    if not user_id: return
    try:
        conn = get_db()
        conn.execute('INSERT INTO logs (user_id, action, details) VALUES (?, ?, ?)', (user_id, action, details))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Erro ao salvar log: {e}")

import re
BAD_WORDS = ['merda', 'porra', 'caralho', 'buceta', 'fuder', 'foder', 'puta', 'puto', 'cuzao', 'cuzão', 'arrombado', 'corno', 'viado', 'bosta', 'cacete', 'fdp', 'boquete', 'viadinho']
def profanity_filter(text):
    if not text: return text
    for word in BAD_WORDS:
        pattern = re.compile(r'\b{}\b'.format(word), re.IGNORECASE)
        # Substitui pela mesma quantidade de hashtags ex: merda -> #####
        text = pattern.sub(lambda m: '#' * len(m.group(0)), text)
    return text
app.jinja_env.filters['censor'] = profanity_filter

@app.before_request
def load_settings():
    conn = get_db()
    settings_rows = conn.execute('SELECT key, value FROM settings').fetchall()
    g.settings = {row['key']: row['value'] for row in settings_rows}
    
    # Track Daily Access (Silent fail if table not ready)
    try:
        today = datetime.date.today().isoformat()
        try:
            conn.execute('INSERT OR IGNORE INTO daily_access (access_date, count) VALUES (?, 0)', (today,))
            conn.execute('UPDATE daily_access SET count = count + 1 WHERE access_date = ?', (today,))
            conn.commit()
        except:
            pass
    except: pass
    
    conn.close()

@app.route('/')
def index(): return render_template('index.html')

@app.route('/materiais')
@app.route('/materiais/<int:folder_id>')
def materiais(folder_id=None):
    conn = get_db()
    breadcrumbs = []
    current_folder = None
    if folder_id:
        curr = folder_id
        while curr:
            f = conn.execute('SELECT * FROM folders WHERE id = ?', (curr,)).fetchone()
            if f:
                breadcrumbs.insert(0, f)
                if current_folder is None: current_folder = f
                curr = f['parent_id']
            else: break
                
    if folder_id:
        subfolders = conn.execute('SELECT * FROM folders WHERE parent_id = ? ORDER BY name', (folder_id,)).fetchall()
        files = conn.execute('SELECT * FROM files WHERE folder_id = ? ORDER BY filename', (folder_id,)).fetchall()
    else:
        subfolders = conn.execute('SELECT * FROM folders WHERE parent_id IS NULL ORDER BY name').fetchall()
        files = conn.execute('SELECT * FROM files WHERE folder_id IS NULL ORDER BY filename').fetchall()
        
    # Get Exams for this folder
    exams = conn.execute('''
        SELECT * FROM exams 
        WHERE (folder_id = ? OR (folder_id IS NULL AND ? IS NULL))
        AND (is_visible = 1)
    ''', (folder_id, folder_id)).fetchall()
    
    conn.close()
    return render_template('materiais.html', current_folder=current_folder, breadcrumbs=breadcrumbs, subfolders=subfolders, files=files, exams=exams)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        conn = get_db()
        user = conn.execute('SELECT * FROM users WHERE email = ?', (email,)).fetchone()
        conn.close()
        
        if user and check_password_hash(user['password_hash'], password):
            session['user_id'] = user['id']
            session['role'] = user['role']
            session['email'] = user['email']
            session['name'] = user['name'] or user['email']
            log_action(user['id'], 'Login', f"Usuário {user['email']} entrou no sistema")
            return redirect(url_for('admin'))
        else:
            flash('Login inválido', 'error')
            
    return render_template('login.html')

@app.route('/logout')
def logout():
    log_action(session.get('user_id'), 'Logout', f"Usuário {session.get('email')} saiu do sistema")
    session.clear()
    return redirect(url_for('index'))

@app.route('/admin')
def admin():
    if 'user_id' not in session: return redirect(url_for('login'))
        
    conn = get_db()
    all_folders = conn.execute('SELECT * FROM folders').fetchall()
    users = conn.execute('SELECT * FROM users ORDER BY created_at DESC').fetchall()
    forums = conn.execute('SELECT * FROM forums ORDER BY created_at DESC').fetchall()
    files = conn.execute('''
        SELECT f.*, u.email as uploader_email, fold.name as folder_name 
        FROM files f LEFT JOIN users u ON f.uploaded_by = u.id 
        LEFT JOIN folders fold ON f.folder_id = fold.id 
        ORDER BY f.uploaded_at DESC
    ''').fetchall()

    try:
        topicos_pendentes = conn.execute('''
            SELECT t.*, f.title as forum_name FROM topics t
            JOIN forums f ON t.forum_id = f.id
            WHERE t.status = 'aguardando' ORDER BY t.created_at DESC
        ''').fetchall()
        topicos_respondidos = conn.execute('''
            SELECT t.*, f.title as forum_name FROM topics t
            JOIN forums f ON t.forum_id = f.id
            WHERE t.status = 'respondido' ORDER BY t.created_at DESC
        ''').fetchall()
        
        # Stats for Admin
        try:
            today = datetime.date.today().isoformat()
            count_row = conn.execute('SELECT count FROM daily_access WHERE access_date = ?', (today,)).fetchone()
            daily_hits = count_row['count'] if count_row else 0
            
            downloads_row = conn.execute('SELECT SUM(download_count) as total FROM files').fetchone()
            total_downloads = downloads_row['total'] if downloads_row and downloads_row['total'] else 0
        except:
            daily_hits = 0
            total_downloads = 0
        
    except sqlite3.OperationalError:
        topicos_pendentes = [] # Tratamento em caso do banco ainda não migrado
        topicos_respondidos = []
        
    conn.close()
    return render_template('admin.html', 
                           users=users, all_folders=all_folders, forums=forums, files=files, 
                           topicos_pendentes=topicos_pendentes, topicos_respondidos=topicos_respondidos,
                           daily_hits=daily_hits, total_downloads=total_downloads)

@app.route('/admin/profile', methods=['POST'])
def edit_profile():
    if 'user_id' not in session: return redirect(url_for('login'))
    user_id = session['user_id']
    name = request.form.get('name')
    password = request.form.get('password')
    conn = get_db()
    
    if name:
        conn.execute('UPDATE users SET name = ? WHERE id = ?', (name, user_id))
        session['name'] = name
        
    if password and password.strip() != '':
        conn.execute('UPDATE users SET password_hash = ? WHERE id = ?', (generate_password_hash(password), user_id))
        
    if 'profile_pic' in request.files:
        file = request.files['profile_pic']
        if file and file.filename != '' and allowed_file(file.filename):
            filename = secure_filename(f"avatar_{user_id}_{file.filename}")
            img_dir = os.path.join(app.config['UPLOAD_FOLDER'], 'avatars')
            os.makedirs(img_dir, exist_ok=True)
            filepath = os.path.join(img_dir, filename)
            file.save(filepath)
            pic_url = url_for('static', filename='uploads/avatars/' + filename)
            conn.execute('UPDATE users SET profile_pic = ? WHERE id = ?', (pic_url, user_id))
            session['profile_pic'] = pic_url
            
    conn.commit()
    conn.close()
    log_action(user_id, 'Atualizou Perfil', f"Nome: {name}")
    flash('Seu perfil foi atualizado com sucesso!', 'success')
    return redirect(url_for('admin'))

@app.route('/admin/remove_banner', methods=['POST'])
def remove_banner():
    if 'user_id' not in session: return redirect(url_for('login'))
    conn = get_db()
    conn.execute("DELETE FROM settings WHERE key = 'home_image_url'")
    conn.commit()
    conn.close()
    log_action(session.get('user_id'), 'Removeu Banner', "Removeu a capa da página inicial")
    flash('Capa do site explodida! Visual original restaurado.', 'success')
    return redirect(url_for('admin'))

@app.route('/admin/upload', methods=['POST'])
def admin_upload():
    if 'user_id' not in session: return redirect(url_for('login'))
    if 'file' in request.files:
        file = request.files['file']
        folder_id = request.form.get('folder_id')
        if not folder_id: folder_id = None
        
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)
            size = os.path.getsize(filepath)
            
            conn = get_db()
            conn.execute('INSERT INTO files (filename, filepath, size, folder_id, uploaded_by) VALUES (?, ?, ?, ?, ?)',
                         (file.filename, filename, size, folder_id, session['user_id']))
            conn.commit()
            conn.close()
            log_action(session['user_id'], 'Subiu Arquivo', f"Novo material: {file.filename}")
            flash('Arquivo enviado!', 'success')
        else:
            flash('Arquivo inválido ou extensão não permitida', 'error')
    return redirect(url_for('admin'))

@app.route('/admin/create_folder', methods=['POST'])
def create_folder():
    if 'user_id' not in session: return redirect(url_for('login'))
    name = request.form.get('name')
    parent_id = request.form.get('parent_id')
    if not parent_id: parent_id = None
    if name:
        conn = get_db()
        conn.execute('INSERT INTO folders (name, parent_id) VALUES (?, ?)', (name, parent_id))
        conn.commit()
        conn.close()
        log_action(session['user_id'], 'Adicionou Pasta', f"Criou pasta: {name}")
        flash('Pasta criada!', 'success')
    return redirect(url_for('admin'))

@app.route('/admin/delete_folder', methods=['POST'])
def delete_folder():
    if 'user_id' not in session: return redirect(url_for('login'))
    folder_id = request.form.get('folder_id')
    if folder_id:
        conn = get_db()
        # Apaga os arquivos físicos
        files = conn.execute('SELECT filepath FROM files WHERE folder_id = ?', (folder_id,)).fetchall()
        for f in files:
            try: os.remove(os.path.join(app.config['UPLOAD_FOLDER'], f['filepath']))
            except Exception: pass
        conn.execute('DELETE FROM files WHERE folder_id = ?', (folder_id,))
        # Apaga subpastas diretas e a própria pasta
        conn.execute('DELETE FROM folders WHERE parent_id = ?', (folder_id,))
        conn.execute('DELETE FROM folders WHERE id = ?', (folder_id,))
        conn.commit()
        conn.close()
        log_action(session['user_id'], 'Removeu Pasta', f"Deletou pasta ID: {folder_id}")
        flash('Pasta e conteúdos excluídos com sucesso!', 'success')
    return redirect(url_for('admin'))

@app.route('/admin/settings', methods=['POST'])
def save_settings():
    if 'user_id' not in session: return redirect(url_for('login'))
    conn = get_db()
    for key in ['site_name', 'primary_color', 'home_announcement', 'home_about', 'instagram_url']:
        val = request.form.get(key)
        if val is not None:
            conn.execute("INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=?", (key, val, val))
            
    if 'home_image' in request.files:
        file = request.files['home_image']
        if file and hasattr(file, 'filename') and file.filename != '' and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            filepath = os.path.join('static', 'images', filename)
            file.save(filepath)
            img_url = url_for('static', filename='images/' + filename)
            conn.execute("INSERT INTO settings (key, value) VALUES ('home_image_url', ?) ON CONFLICT(key) DO UPDATE SET value=?", (img_url, img_url))
            
    conn.commit()
    conn.close()
    log_action(session['user_id'], 'Alterou Configurações', "Mudou cores/textos globais")
    flash('Configurações atualizadas para o site!', 'success')
    return redirect(url_for('admin'))

@app.route('/admin/add_user', methods=['POST'])
def add_user():
    if 'user_id' not in session: return redirect(url_for('login'))
    name = request.form.get('name', 'Professor Auxiliar')
    email = request.form['email']
    password = request.form['password']
    role = request.form.get('role', 'admin') # master or admin
    
    # Only developer or master can add users
    if session.get('role') not in ['developer', 'master']:
        flash('Sem permissão para adicionar administradores.', 'error')
        return redirect(url_for('admin'))
        
    conn = get_db()
    try:
        conn.execute('INSERT INTO users (email, password_hash, name, role) VALUES (?, ?, ?, ?)',
                     (email, generate_password_hash(password), name, role))
        conn.commit()
        log_action(session['user_id'], f'Adicionou {role.upper()}', f"Recrutou: {email}")
        flash(f'Administrador ({role}) adicionado!', 'success')
    except sqlite3.IntegrityError:
        flash('Email já existe.', 'error')
    finally:
        conn.close()
    return redirect(url_for('admin'))

@app.route('/admin/delete_user/<int:user_id>', methods=['POST'])
def delete_user(user_id):
    current_role = session.get('role')
    current_user_id = session.get('user_id')
    
    if current_role not in ['developer', 'master']:
        flash('Você não tem permissão para isso.', 'error')
        return redirect(url_for('admin'))
        
    conn = get_db()
    target = conn.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()
    
    if not target:
        conn.close()
        return redirect(url_for('admin'))
        
    can_delete = False
    if current_role == 'developer':
        if target['id'] != current_user_id: # Cannot delete self
            can_delete = True
    elif current_role == 'master':
        if target['role'] == 'admin':
            can_delete = True
            
    if can_delete:
        conn.execute('DELETE FROM users WHERE id = ?', (user_id,))
        conn.commit()
        log_action(current_user_id, 'Banir Admin', f"Removeu acesso de: {target['email']} ({target['role']})")
        flash('Conta excluída com sucesso.', 'success')
    else:
        flash('Você não pode excluir esse nível de acesso.', 'error')
        
    conn.close()
    return redirect(url_for('admin'))

@app.route('/admin/create_forum', methods=['POST'])
def create_forum():
    if 'user_id' not in session: return redirect(url_for('login'))
    title = request.form.get('title')
    description = request.form.get('description')
    if title:
        conn = get_db()
        conn.execute('INSERT INTO forums (title, description) VALUES (?, ?)', (title, description))
        conn.commit()
        conn.close()
        log_action(session['user_id'], 'Abriu Sala Fórum', f"Sala: {title}")
        flash('Sala de Fórum criada!', 'success')
    return redirect(url_for('admin'))

@app.route('/admin/delete_forum/<int:forum_id>', methods=['POST'])
def delete_forum(forum_id):
    if 'user_id' not in session: return redirect(url_for('login'))
    conn = get_db()
    conn.execute('DELETE FROM forums WHERE id = ?', (forum_id,))
    conn.commit()
    conn.close()
    log_action(session['user_id'], 'Removeu Sala Fórum', f"Sala ID: {forum_id}")
    flash('Sala removida.', 'success')
    return redirect(url_for('admin'))

@app.route('/admin/delete_topic/<int:topic_id>', methods=['POST'])
def delete_topic(topic_id):
    if 'user_id' not in session: return redirect(url_for('login'))
    forum_id = request.form.get('forum_id')
    conn = get_db()
    msgs = conn.execute('SELECT file_path FROM messages WHERE topic_id = ?', (topic_id,)).fetchall()
    for m in msgs:
        if m['file_path']:
            try: os.remove(os.path.join(app.config['UPLOAD_FOLDER'], 'forum', m['file_path']))
            except Exception: pass
            
    conn.execute('DELETE FROM messages WHERE topic_id = ?', (topic_id,))
    conn.execute('DELETE FROM topics WHERE id = ?', (topic_id,))
    conn.commit()
    conn.close()
    log_action(session['user_id'], 'Deletou Discussão', f"Tópico ID: {topic_id}")
    flash('Discussão apagada com sucesso.', 'success')
    if forum_id: return redirect(url_for('view_forum', forum_id=forum_id))
    return redirect(url_for('admin'))

@app.route('/forum', methods=['GET'])
def forums():
    conn = get_db()
    forums = conn.execute('SELECT * FROM forums ORDER BY created_at DESC').fetchall()
    conn.close()
    return render_template('forum.html', forums=forums)

@app.route('/forum/<int:forum_id>', methods=['GET', 'POST'])
def view_forum(forum_id):
    conn = get_db()
    if request.method == 'POST':
        title = request.form.get('title')
        content = request.form.get('content')
        author_name = request.form.get('author_name', 'Anônimo Estudante')
        
        is_admin = 'user_id' in session
        user_id = session.get('user_id') if is_admin else None
        if is_admin: author_name = session.get('name') or session['email']
        
        file_path = None
        if 'file' in request.files:
            file = request.files['file']
            if file and file.filename != '' and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                full_path = os.path.join(app.config['UPLOAD_FOLDER'], 'forum', filename)
                file.save(full_path)
                file_path = filename
                
        cursor = conn.execute("INSERT INTO topics (forum_id, title, author_name, status) VALUES (?, ?, ?, ?)", (forum_id, title, author_name, 'respondido' if is_admin else 'aguardando'))
        topic_id = cursor.lastrowid
        
        # Injeção manual se backend for mais velho 
        try: conn.execute('INSERT INTO messages (topic_id, author_name, content, is_admin, file_path, user_id) VALUES (?, ?, ?, ?, ?, ?)', (topic_id, author_name, content, is_admin, file_path, user_id))
        except sqlite3.OperationalError: conn.execute('INSERT INTO messages (topic_id, author_name, content, is_admin, file_path) VALUES (?, ?, ?, ?, ?)', (topic_id, author_name, content, is_admin, file_path))
            
        conn.commit()
        log_action(user_id, 'Helpdesk Atendeu' if is_admin else 'Fórum Novo Tópico', f"Título: {title}")
        return redirect(url_for('view_topic', topic_id=topic_id))

    forum = conn.execute('SELECT * FROM forums WHERE id = ?', (forum_id,)).fetchone()
    try: topics = conn.execute('SELECT * FROM topics WHERE forum_id = ? ORDER BY created_at DESC', (forum_id,)).fetchall()
    except sqlite3.OperationalError: topics = []
    conn.close()
    return render_template('topics.html', forum=forum, topics=topics)

@app.route('/topic/<int:topic_id>', methods=['GET', 'POST'])
def view_topic(topic_id):
    conn = get_db()
    topic = conn.execute('SELECT * FROM topics WHERE id = ?', (topic_id,)).fetchone()
    
    if request.method == 'POST':
        content = request.form.get('content')
        author_name = request.form.get('author_name', 'Estudante Anônimo')
        reply_to_id = request.form.get('reply_to_id')
        if not reply_to_id: reply_to_id = None
        
        is_admin = 'user_id' in session
        user_id = session.get('user_id') if is_admin else None
        if is_admin: author_name = session.get('name') or session['email']
            
        file_path = None
        if 'file' in request.files:
            file = request.files['file']
            if file and file.filename != '' and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                full_path = os.path.join(app.config['UPLOAD_FOLDER'], 'forum', filename)
                file.save(full_path)
                file_path = filename
                
        try: conn.execute('INSERT INTO messages (topic_id, author_name, content, is_admin, file_path, reply_to_id, user_id) VALUES (?, ?, ?, ?, ?, ?, ?)', (topic_id, author_name, content, is_admin, file_path, reply_to_id, user_id))
        except sqlite3.OperationalError: conn.execute('INSERT INTO messages (topic_id, author_name, content, is_admin, file_path, reply_to_id) VALUES (?, ?, ?, ?, ?, ?)', (topic_id, author_name, content, is_admin, file_path, reply_to_id))
                     
        new_status = 'respondido' if is_admin else 'aguardando'
        try: conn.execute("UPDATE topics SET status = ? WHERE id = ?", (new_status, topic_id))
        except sqlite3.OperationalError: pass
        
        conn.commit()
        log_action(user_id, 'Helpdesk Respondeu' if is_admin else 'Fórum Mensagem', f"No tópico ID: {topic_id}")
        return redirect(url_for('view_topic', topic_id=topic_id))
        
    try:
        messages = conn.execute('''
            SELECT m1.*, m2.content as reply_to_content, m2.author_name as reply_to_author, 
                   u.profile_pic as admin_pic, u.name as admin_name, u.role as admin_role
            FROM messages m1 
            LEFT JOIN messages m2 ON m1.reply_to_id = m2.id 
            LEFT JOIN users u ON m1.user_id = u.id
            WHERE m1.topic_id = ? ORDER BY m1.created_at ASC
        ''', (topic_id,)).fetchall()
    except sqlite3.OperationalError:
        messages = conn.execute('''
            SELECT m1.*, m2.content as reply_to_content, m2.author_name as reply_to_author 
            FROM messages m1 LEFT JOIN messages m2 ON m1.reply_to_id = m2.id 
            WHERE m1.topic_id = ? ORDER BY m1.created_at ASC
        ''', (topic_id,)).fetchall()
        
    conn.close()
    return render_template('messages.html', topic=topic, messages=messages)

@app.route('/admin/delete_message/<int:msg_id>', methods=['POST'])
def delete_message(msg_id):
    if 'user_id' not in session: return redirect(url_for('login'))
    topic_id = request.form.get('topic_id')
    conn = get_db()
    msg_record = conn.execute('SELECT file_path FROM messages WHERE id = ?', (msg_id,)).fetchone()
    if msg_record and msg_record['file_path']:
        try: os.remove(os.path.join(app.config['UPLOAD_FOLDER'], 'forum', msg_record['file_path']))
        except Exception: pass
        
    conn.execute('DELETE FROM messages WHERE id = ?', (msg_id,))
    conn.commit()
    conn.close()
    log_action(session['user_id'], 'Forum Moderou Mensagem', f"ID: {msg_id}")
    flash('Moderação ativada. Mensagem varrida do fórum.', 'success')
    return redirect(url_for('view_topic', topic_id=topic_id))

@app.route('/admin/delete_file/<int:file_id>', methods=['POST'])
def delete_file(file_id):
    if 'user_id' not in session: return redirect(url_for('login'))
    conn = get_db()
    file_record = conn.execute('SELECT * FROM files WHERE id = ?', (file_id,)).fetchone()
    if file_record:
        try: 
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], file_record['filepath'])
            if os.path.exists(filepath): os.remove(filepath)
        except Exception as e: pass
            
        conn.execute('DELETE FROM files WHERE id = ?', (file_id,))
        conn.commit()
        log_action(session['user_id'], 'Removeu Arquivo', f"Deletou arquivo ID: {file_id}")
        flash('PDF removido com sucesso!', 'success')
    conn.close()
    return redirect(url_for('admin'))

@app.route('/download/<int:file_id>')
def download(file_id):
    conn = get_db()
    conn.execute('UPDATE files SET download_count = download_count + 1 WHERE id = ?', (file_id,))
    conn.commit()
    file_record = conn.execute('SELECT * FROM files WHERE id = ?', (file_id,)).fetchone()
    conn.close()
    if file_record:
        return send_from_directory(app.config['UPLOAD_FOLDER'], file_record['filepath'], as_attachment=True, download_name=file_record['filename'])
    return 'Arquivo nulo', 404
    
@app.route('/download_forum/<filename>')
def download_forum(filename): return send_from_directory(os.path.join(app.config['UPLOAD_FOLDER'], 'forum'), secure_filename(filename), as_attachment=True)

with app.app_context():
    init_db()  # Ensure tables exist
    conn = get_db()
    
    # Robust Migrations for Render (SQLite and Gunicorn safe)
    try: conn.execute('ALTER TABLE users ADD COLUMN name TEXT'); conn.commit()
    except: pass
    try: conn.execute('ALTER TABLE users ADD COLUMN role TEXT DEFAULT "admin"'); conn.commit()
    except: pass
    try: conn.execute('ALTER TABLE bug_reports ADD COLUMN is_resolved BOOLEAN DEFAULT 0'); conn.commit()
    except: pass
    try: conn.execute('ALTER TABLE exams ADD COLUMN pdf_path TEXT'); conn.commit()
    except: pass
    try: conn.execute('ALTER TABLE exam_questions ADD COLUMN resolution_text TEXT'); conn.commit()
    except: pass
    
    # Garantir Tabelas de Estatísticas
    conn.execute('''CREATE TABLE IF NOT EXISTS exam_submissions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        exam_id INTEGER NOT NULL,
        student_name TEXT NOT NULL,
        score INTEGER NOT NULL,
        total_questions INTEGER NOT NULL,
        percentage REAL NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    conn.execute('''CREATE TABLE IF NOT EXISTS submission_details (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        submission_id INTEGER NOT NULL,
        question_id INTEGER NOT NULL,
        is_correct BOOLEAN NOT NULL,
        user_choice TEXT,
        FOREIGN KEY(submission_id) REFERENCES exam_submissions(id) ON DELETE CASCADE
    )''')
    try: conn.execute('CREATE TABLE IF NOT EXISTS daily_access (access_date DATE PRIMARY KEY, count INTEGER DEFAULT 0)')
    except: pass
    try: conn.execute('ALTER TABLE files ADD COLUMN download_count INTEGER DEFAULT 0')
    except: pass
    try: conn.execute('ALTER TABLE exams ADD COLUMN is_visible BOOLEAN DEFAULT 0')
    except: pass
    # Migrations para exam_submissions (caso a tabela já existisse sem essas colunas)
    try: conn.execute('ALTER TABLE exam_submissions ADD COLUMN total_questions INTEGER DEFAULT 0')
    except: pass
    try: conn.execute('ALTER TABLE exam_submissions ADD COLUMN percentage REAL DEFAULT 0')
    except: pass
    conn.commit()
    
    # Forçar dados do DESENVOLVEDOR...
    dev_exists = conn.execute('SELECT * FROM users WHERE email = ?', ('desenvolper@fkn.com',)).fetchone()
    if not dev_exists:
        conn.execute('INSERT INTO users (email, password_hash, name, role) VALUES (?, ?, ?, ?)',
                     ('desenvolper@fkn.com', generate_password_hash('Praxair1'), 'Desenvolvedor Master', 'developer'))
    else:
        conn.execute('UPDATE users SET password_hash = ?, role = "developer", name = "Desenvolvedor Master" WHERE email = ?',
                     (generate_password_hash('Praxair1'), 'desenvolper@fkn.com'))
        
    # Garantir MASTER (Agora chamado de Professor)
    master_exists = conn.execute('SELECT * FROM users WHERE email = ?', ('admin@admin.com',)).fetchone()
    if not master_exists:
        conn.execute('INSERT INTO users (email, password_hash, name, role) VALUES (?, ?, ?, ?)',
                     ('admin@admin.com', generate_password_hash('123456'), 'Professor', 'master'))
    else:
        # Garantir o papel de master e o nome Professor se não tiver mudado
        conn.execute('UPDATE users SET role = "master", name = "Professor" WHERE email = ? AND name = "Fundador Oficial"', ('admin@admin.com',))
        conn.execute('UPDATE users SET role = "master" WHERE email = ?', ('admin@admin.com',))
        
    conn.commit()
    conn.close()

@app.route('/admin/logs')
def admin_logs():
    if 'user_id' not in session: return redirect(url_for('login'))
    conn = get_db()
    logs = conn.execute('''
        SELECT logs.*, users.name as user_name, users.email as user_email 
        FROM logs 
        LEFT JOIN users ON logs.user_id = users.id 
        ORDER BY logs.created_at DESC 
        LIMIT 500
    ''').fetchall()
    conn.close()
    return render_template('admin_logs.html', logs=logs)


@app.route('/faq')
def faq():
    conn = get_db()
    faqs = conn.execute('SELECT * FROM faqs ORDER BY order_num ASC').fetchall()
    conn.close()
    return render_template('faq.html', faqs=faqs)

@app.route('/report_bug', methods=['POST'])
def report_bug():
    message = request.form.get('message')
    file = request.files.get('file')
    filename = None
    if file and file.filename != '' and allowed_file(file.filename):
        os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], 'bugs'), exist_ok=True)
        filename = secure_filename(f"bug_{int(time.time())}_{file.filename}")
        file.save(os.path.join(app.config['UPLOAD_FOLDER'], 'bugs', filename))
    
    conn = get_db()
    conn.execute('INSERT INTO bug_reports (message, attachment_path) VALUES (?, ?)', (message, filename))
    conn.commit()
    conn.close()
    flash('Denúncia enviada! Nossa equipe de TI vai verificar em breve.', 'success')
    return redirect(request.referrer or url_for('index'))

@app.route('/admin/reports')
def view_reports():
    if 'user_id' not in session: return redirect(url_for('login'))
    conn = get_db()
    reports = conn.execute('SELECT * FROM bug_reports ORDER BY is_resolved ASC, created_at DESC').fetchall()
    conn.close()
    return render_template('admin_reports.html', reports=reports)

@app.route('/admin/reports/<int:report_id>/resolve', methods=['POST'])
def resolve_bug(report_id):
    if 'user_id' not in session: return redirect(url_for('login'))
    conn = get_db()
    conn.execute('UPDATE bug_reports SET is_resolved = 1 WHERE id = ?', (report_id,))
    conn.commit()
    conn.close()
    flash('Erro marcado como resolvido!', 'success')
    return redirect(url_for('admin_reports'))

@app.route('/admin/dev_panel', methods=['GET', 'POST'])
def dev_panel():
    if session.get('role') != 'developer': 
        flash('Acesso restrito ao Desenvolvedor Master.', 'error')
        return redirect(url_for('admin'))
    
    conn = get_db()
    if request.method == 'POST':
        keys = ['dev_instagram_url', 'dev_name', 'show_dev_name', 'x_url', 'facebook_url', 'whatsapp_url', 'footer_rights']
        for k in keys:
            val = request.form.get(k, '')
            conn.execute('INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=?', (k, val, val))
        conn.commit()
        flash('DADOS DO DESENVOLVEDOR ATUALIZADOS!', 'success')
        return redirect(url_for('dev_panel'))
        
    conn.close()
    return render_template('dev_panel.html')

@app.route('/admin/faqs', methods=['GET', 'POST', 'DELETE'])
def admin_faqs():
    if 'user_id' not in session: return redirect(url_for('login'))
    conn = get_db()
    if request.method == 'POST':
        question = request.form.get('question')
        answer = request.form.get('answer')
        keyword = request.form.get('keyword')
        redirect_url = request.form.get('redirect_url')
        conn.execute('INSERT INTO faqs (question, answer, keyword, redirect_url) VALUES (?, ?, ?, ?)', (question, answer, keyword, redirect_url))
        conn.commit()
        flash('FAQ Adicionada!', 'success')
    
    faqs = conn.execute('SELECT * FROM faqs ORDER BY order_num ASC').fetchall()
    conn.close()
    return render_template('admin_faqs.html', faqs=faqs)

@app.route('/admin/exams/<int:exam_id>/manage', methods=['GET', 'POST'])
def manage_exam(exam_id):
    if 'user_id' not in session: return redirect(url_for('login'))
    conn = get_db()
    exam = conn.execute('SELECT * FROM exams WHERE id = ?', (exam_id,)).fetchone()
    
    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'update_details':
            title = request.form.get('title')
            folder_id = request.form.get('folder_id')
            is_visible = 1 if request.form.get('is_visible') else 0
            
            if not folder_id: folder_id = None
            
            conn.execute('UPDATE exams SET title = ?, folder_id = ?, is_visible = ? WHERE id = ?', 
                         (title, folder_id, is_visible, exam_id))
            conn.commit()
            flash('Simulado atualizado!', 'success')
            
        elif action == 'delete_exam':
            conn.execute('DELETE FROM exams WHERE id = ?', (exam_id,))
            conn.commit()
            conn.close()
            flash('Simulado removido permanentemente!', 'success')
            return redirect(url_for('admin_exams'))
            
    # Get questions for this exam
    questions = conn.execute('SELECT * FROM exam_questions WHERE exam_id = ?', (exam_id,)).fetchall()
    folders = conn.execute('SELECT * FROM folders').fetchall()
    conn.close()
    return render_template('admin_manage_exam.html', exam=exam, questions=questions, folders=folders)

@app.route('/admin/exams', methods=['GET', 'POST'])
def admin_exams():
    if 'user_id' not in session: return redirect(url_for('login'))
    conn = get_db()
    if request.method == 'POST':
        title = request.form.get('title')
        folder_id = request.form.get('folder_id')
        pdf_file = request.files.get('pdf_file')
        if not folder_id: folder_id = None
        
        pdf_filename = None
        if pdf_file and pdf_file.filename != '' and allowed_file(pdf_file.filename):
            os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], 'exams'), exist_ok=True)
            pdf_filename = secure_filename(f"pdf_{int(time.time())}_{pdf_file.filename}")
            pdf_file.save(os.path.join(app.config['UPLOAD_FOLDER'], 'exams', pdf_filename))
        
        conn.execute('INSERT INTO exams (title, folder_id, pdf_path, is_visible) VALUES (?, ?, ?, 0)', (title, folder_id, pdf_filename))
        conn.commit()
        flash('Modo Prova Criado! Ele iniciará como OCULTO.', 'success')
    
    exams_raw = conn.execute('SELECT * FROM exams ORDER BY created_at DESC').fetchall()
    exams = []
    for e in exams_raw:
        e_dict = dict(e)
        e_dict['questions'] = conn.execute('SELECT * FROM exam_questions WHERE exam_id = ?', (e['id'],)).fetchall()
        exams.append(e_dict)
        
    folders = conn.execute('SELECT * FROM folders').fetchall()
    conn.close()
    return render_template('admin_exams.html', exams=exams, folders=folders)

@app.route('/admin/exams/<int:exam_id>/update_question/<int:question_id>', methods=['POST'])
def update_question(exam_id, question_id):
    if 'user_id' not in session: return redirect(url_for('login'))
    new_option = request.form.get('correct_option')
    conn = get_db()
    conn.execute('UPDATE exam_questions SET correct_option = ? WHERE id = ?', (new_option, question_id))
    conn.commit()
    conn.close()
    flash('Gabarito da questão atualizado!', 'success')
    return redirect(url_for('manage_exam', exam_id=exam_id))

@app.route('/admin/exams/<int:exam_id>/delete_question/<int:question_id>', methods=['POST'])
def delete_question(exam_id, question_id):
    if 'user_id' not in session: return redirect(url_for('login'))
    conn = get_db()
    q = conn.execute('SELECT * FROM exam_questions WHERE id = ?', (question_id,)).fetchone()
    if q:
        if q['question_image']:
            try: os.remove(os.path.join(app.config['UPLOAD_FOLDER'], 'exams', q['question_image']))
            except: pass
        if q['resolution_image']:
            try: os.remove(os.path.join(app.config['UPLOAD_FOLDER'], 'exams', q['resolution_image']))
            except: pass
        conn.execute('DELETE FROM exam_questions WHERE id = ?', (question_id,))
        conn.commit()
    conn.close()
    flash('Questão removida!', 'success')
    return redirect(url_for('admin_exams'))

@app.route('/admin/exams/<int:exam_id>/add_question', methods=['POST'])
def add_question(exam_id):
    if 'user_id' not in session: return redirect(url_for('login'))
    q_file = request.files.get('question_image')
    r_file = request.files.get('resolution_image')
    r_text = request.form.get('resolution_text')
    correct_option = request.form.get('correct_option', 'A')
    
    q_filename = None
    r_filename = None
    os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], 'exams'), exist_ok=True)
    
    if q_file and q_file.filename != '' and allowed_file(q_file.filename):
        q_filename = secure_filename(f"q_{exam_id}_{int(time.time())}_{q_file.filename}")
        q_file.save(os.path.join(app.config['UPLOAD_FOLDER'], 'exams', q_filename))
    
    if r_file and r_file.filename != '' and allowed_file(r_file.filename):
        r_filename = secure_filename(f"r_{exam_id}_{int(time.time())}_{r_file.filename}")
        r_file.save(os.path.join(app.config['UPLOAD_FOLDER'], 'exams', r_filename))
        
    conn = get_db()
    conn.execute('INSERT INTO exam_questions (exam_id, question_image, resolution_image, resolution_text, correct_option) VALUES (?, ?, ?, ?, ?)', (exam_id, q_filename, r_filename, r_text, correct_option))
    conn.commit()
    conn.close()
    flash('Questão Adicionada!', 'success')
    return redirect(url_for('manage_exam', exam_id=exam_id))

@app.route('/admin/exams/<int:exam_id>/add_multiple', methods=['POST'])
def add_multiple_questions(exam_id):
    if 'user_id' not in session: return redirect(url_for('login'))
    gabarito_text = request.form.get('gabarito_text', '').upper().replace(',', ' ').replace(';', ' ')
    options = gabarito_text.split()
    
    conn = get_db()
    for opt in options:
        if opt in ['A', 'B', 'C', 'D', 'E']:
            conn.execute('INSERT INTO exam_questions (exam_id, correct_option) VALUES (?, ?)', (exam_id, opt))
    conn.commit()
    conn.close()
    flash(f'{len(options)} questões adicionadas ao gabarito rápido!', 'success')
    return redirect(url_for('manage_exam', exam_id=exam_id))

@app.route('/exam/<int:exam_id>', methods=['GET', 'POST'])
def view_exam(exam_id):
    conn = get_db()
    exam = conn.execute('SELECT * FROM exams WHERE id = ?', (exam_id,)).fetchone()
    if not exam:
        conn.close()
        return "Simulado não encontrado", 404
        
    # Admin can always view
    is_visible = dict(exam).get('is_visible', 0)
    if not is_visible and session.get('role') != 'developer':
        conn.close()
        return render_template('error.html', message="Este simulado está desativado temporariamente pelo professor.")

    questions = conn.execute('SELECT * FROM exam_questions WHERE exam_id = ?', (exam_id,)).fetchall()
    
    if request.method == 'POST':
        student_name = request.form.get('student_name')
        if not student_name:
            flash('Por favor, informe seu nome completo.', 'error')
            return redirect(url_for('view_exam', exam_id=exam_id))
        student_name = student_name if student_name else 'Estudante Anônimo'
        answers = request.form.to_dict()
        results = []
        correct_count = 0
        for q in questions:
            user_ans = answers.get(f'q_{q["id"]}')
            is_correct = (user_ans == q['correct_option'])
            if is_correct: correct_count += 1
            results.append({
                'id': q['id'],
                'user_ans': user_ans,
                'correct_ans': q['correct_option'],
                'is_correct': is_correct,
                'question_image': q['question_image'],
                'resolution_image': q['resolution_image'],
                'resolution_text': q['resolution_text']
            })
        
        # Salvar Submissão para Estatísticas
        total_q = len(questions)
        percentage = (correct_count / total_q * 100) if total_q > 0 else 0
        cur = conn.execute('''
            INSERT INTO exam_submissions (exam_id, student_name, score, total_questions, percentage)
            VALUES (?, ?, ?, ?, ?)
        ''', (exam_id, student_name, correct_count, total_q, percentage))
        submission_id = cur.lastrowid
        
        for r in results:
            conn.execute('''
                INSERT INTO submission_details (submission_id, question_id, is_correct, user_choice)
                VALUES (?, ?, ?, ?)
            ''', (submission_id, r['id'], r['is_correct'], r['user_ans']))
        
        conn.commit()
        conn.close()
        return render_template('exam_result.html', exam=exam, results=results, score=correct_count, total=total_q, student_name=student_name)
        
    conn.close()
    return render_template('exam.html', exam=exam, questions=questions)

@app.route('/admin/exam_stats')
def exam_stats():
    if 'user_id' not in session: return redirect(url_for('login'))
    conn = get_db()
    
    # Médias por Exame
    exam_analysis = conn.execute('''
        SELECT e.id, e.title, 
               AVG(s.percentage) as avg_score, 
               COUNT(s.id) as total_students,
               MAX(s.percentage) as max_score,
               MIN(s.percentage) as min_score
        FROM exams e
        LEFT JOIN exam_submissions s ON e.id = s.exam_id
        GROUP BY e.id
        ORDER BY e.created_at DESC
    ''').fetchall()
    
    # Últimas 50 submissões
    recent_submissions = conn.execute('''
        SELECT s.*, e.title as exam_title
        FROM exam_submissions s
        JOIN exams e ON s.exam_id = e.id
        ORDER BY s.created_at DESC
        LIMIT 50
    ''').fetchall()
    
    # Questões mais erradas (Top 10)
    failed_questions = conn.execute('''
        SELECT q.id, q.exam_id, e.title as exam_title, q.question_image, 
               COUNT(d.id) as total_errors
        FROM exam_questions q
        JOIN exams e ON q.exam_id = e.id
        JOIN submission_details d ON q.id = d.question_id
        WHERE d.is_correct = 0
        GROUP BY q.id
        ORDER BY total_errors DESC
        LIMIT 10
    ''').fetchall()
    
    conn.close()
    return render_template('admin_exam_stats.html', 
                           exam_analysis=exam_analysis, 
                           recent_submissions=recent_submissions,
                           failed_questions=failed_questions)

if __name__ == '__main__': app.run(debug=True, port=5000)
