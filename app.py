from flask import Flask, render_template, request, redirect, url_for, session, send_from_directory, flash, g
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import os
import sqlite3, time, datetime
from database import get_db, init_db, OperationalError, IntegrityError
from supabase import create_client, Client

SUPABASE_URL = os.environ.get('SUPABASE_URL')
SUPABASE_KEY = os.environ.get('SUPABASE_KEY')
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY) if SUPABASE_URL and SUPABASE_KEY else None

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

def supabase_upload(bucket, path, file_content, content_type):
    """Upload para Supabase Storage. Retorna URL pública como string.
    Constrói a URL manualmente para evitar bugs do get_public_url() no supabase-py 2.x"""
    try:
        supabase.storage.from_(bucket).upload(
            path, file_content,
            file_options={"content-type": content_type, "upsert": "true"}
        )
    except Exception as e1:
        print(f"[upload] Primeira tentativa falhou (upsert): {e1}")
        # Arquivo já existe ou upsert falhou: remove e re-envia
        try:
            supabase.storage.from_(bucket).remove([path])
        except Exception:
            pass
        try:
            supabase.storage.from_(bucket).upload(
                path, file_content,
                file_options={"content-type": content_type}
            )
        except Exception as e2:
            print(f"[upload] Erro final no Supabase (verifique RLS policy ou buckets): {e2}")
            return None  # Retorna None para o app fazer fallback local

    # Constrói a URL pública manualmente (evita problema do get_public_url() retornar objeto)
    # Formato Supabase: {URL}/storage/v1/object/public/{bucket}/{path}
    return f"{SUPABASE_URL}/storage/v1/object/public/{bucket}/{path}"

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
    # exams = conn.execute('''
    #     SELECT * FROM exams 
    #     WHERE (folder_id = ? OR (folder_id IS NULL AND ? IS NULL))
    #     AND (is_visible = 1)
    # ''', (folder_id, folder_id)).fetchall()
    
    conn.close()
    return render_template('materiais.html', current_folder=current_folder, breadcrumbs=breadcrumbs, subfolders=subfolders, files=files)

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
            try: session['profile_pic'] = user['profile_pic']
            except: session['profile_pic'] = None
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

    # Early initialization for safety
    topicos_pendentes = []
    topicos_respondidos = []

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
        
    except OperationalError:
        topicos_pendentes = [] 
        topicos_respondidos = []
        
    conn.close()
    return render_template('admin.html', 
                           users=users, all_folders=all_folders, forums=forums, files=files, 
                           topicos_pendentes=topicos_pendentes, topicos_respondidos=topicos_respondidos)

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
            filename = f"avatar_{user_id}_{secure_filename(file.filename)}"
            
            pic_url = None
            if supabase:
                file_content = file.read()
                content_type = file.content_type or 'image/jpeg'
                pic_url = supabase_upload('materiais', f"avatars/{filename}", file_content, content_type)
            
            if not pic_url:
                if supabase: 
                    flash('Erro no Supabase (Verifique o Bucket ou RLS). Salvando imagem localmente.', 'error')
                    file.seek(0)
                # Fallback to local
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
            filename = f"{int(time.time())}_{secure_filename(file.filename)}"
            
            storage_path = None
            if supabase:
                file_content = file.read()
                content_type = file.content_type or 'application/octet-stream'
                file_url = supabase_upload('materiais', filename, file_content, content_type)
                storage_path = file_url
                
            if not storage_path:
                if supabase: 
                    flash('Erro no bucket Supabase. Salvando localmente.', 'error')
                    file.seek(0)
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(filepath)
                storage_path = filename

            size = len(file_content) if supabase else os.path.getsize(filepath)
            
            conn = get_db()
            conn.execute('INSERT INTO files (filename, filepath, size, folder_id, uploaded_by) VALUES (?, ?, ?, ?, ?)',
                         (file.filename, storage_path, size, folder_id, session['user_id']))
            conn.commit()
            conn.close()
            log_action(session['user_id'], 'Subiu Arquivo', f"Novo material: {file.filename}")
            flash('Arquivo enviado para nuvem!', 'success')
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
        files = conn.execute('SELECT filepath FROM files WHERE folder_id = ?', (folder_id,)).fetchall()
        for f in files:
            try:
                if supabase and f['filepath'].startswith('http'):
                    name = f['filepath'].split('/')[-1]
                    supabase.storage.from_('materiais').remove([name])
                else:
                    os.remove(os.path.join(app.config['UPLOAD_FOLDER'], f['filepath']))
            except Exception: pass
        conn.execute('DELETE FROM files WHERE folder_id = ?', (folder_id,))
        conn.execute('DELETE FROM folders WHERE parent_id = ?', (folder_id,))
        conn.execute('DELETE FROM folders WHERE id = ?', (folder_id,))
        conn.commit()
        conn.close()
        flash('Pasta e nuvem limpas!', 'success')
    return redirect(url_for('admin'))

@app.route('/admin/settings', methods=['POST'])
def save_settings():
    if 'user_id' not in session: return redirect(url_for('login'))
    conn = get_db()
    for key in ['site_name', 'primary_color', 'home_announcement', 'home_about', 'instagram_url']:
        val = request.form.get(key)
        if val is not None:
            conn.execute("INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=EXCLUDED.value", (key, val))
            
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
    except IntegrityError:
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
                filename = f"forum_{int(time.time())}_{secure_filename(file.filename)}"
                if supabase:
                    file_content = file.read()
                    content_type = file.content_type or 'application/octet-stream'
                    file_path = supabase_upload('materiais', f"forum/{filename}", file_content, content_type)
                
                if not file_path:
                    if supabase:
                        file.seek(0)
                        flash('Arquivo anexado não pôde ir para a nuvem. Salvando localmente.', 'error')
                    full_path = os.path.join(app.config['UPLOAD_FOLDER'], 'forum', filename)
                    file.save(full_path)
                    file_path = filename
                
        query = "INSERT INTO topics (forum_id, title, author_name, status) VALUES (?, ?, ?, ?) RETURNING id"
        cursor = conn.execute(query, (forum_id, title, author_name, 'respondido' if is_admin else 'aguardando'))
        
        if os.environ.get('DATABASE_URL'):
            topic_id = cursor.fetchone()['id']
        else:
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
                filename = f"forum_{int(time.time())}_{secure_filename(file.filename)}"
                file_path = None
                if supabase:
                    file_content = file.read()
                    content_type = file.content_type or 'application/octet-stream'
                    file_path = supabase_upload('materiais', f"forum/{filename}", file_content, content_type)
                
                if not file_path:
                    if supabase:
                        file.seek(0)
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
    except OperationalError:
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
            if supabase and file_record['filepath'].startswith('http'):
                name = file_record['filepath'].split('/')[-1]
                supabase.storage.from_('materiais').remove([name])
            else:
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], file_record['filepath'])
                if os.path.exists(filepath): os.remove(filepath)
        except Exception: pass
            
        conn.execute('DELETE FROM files WHERE id = ?', (file_id,))
        conn.commit()
        flash('PDF removido da nuvem!', 'success')
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
        if file_record['filepath'].startswith('http'):
            return redirect(file_record['filepath'])
        return send_from_directory(app.config['UPLOAD_FOLDER'], file_record['filepath'], as_attachment=True, download_name=file_record['filename'])
    return 'Arquivo nulo', 404
    
@app.route('/download_forum/<filename>')
def download_forum(filename): return send_from_directory(os.path.join(app.config['UPLOAD_FOLDER'], 'forum'), secure_filename(filename), as_attachment=True)

with app.app_context():
    init_db()  # Ensure tables exist e schema atualizado
    
    # Rota adicional para deletar FAQ
    @app.route('/admin/faqs/delete/<int:faq_id>', methods=['POST'])
    def delete_faq(faq_id):
        if 'user_id' not in session: return redirect(url_for('login'))
        conn = get_db()
        conn.execute('DELETE FROM faqs WHERE id = ?', (faq_id,))
        conn.commit()
        conn.close()
        flash('Pergunta removida com sucesso.', 'success')
        return redirect(url_for('admin_faqs'))

    # Rota adicional para editar FAQ
    @app.route('/admin/faqs/edit/<int:faq_id>', methods=['POST'])
    def edit_faq(faq_id):
        if 'user_id' not in session: return redirect(url_for('login'))
        question = request.form['question']
        answer = request.form['answer']
        keyword = request.form.get('keyword', '')
        redirect_url = request.form.get('redirect_url', '')
        keyword_color = request.form.get('keyword_color', '#eab308')
        
        conn = get_db()
        conn.execute('UPDATE faqs SET question=?, answer=?, keyword=?, redirect_url=?, keyword_color=? WHERE id=?', 
                     (question, answer, keyword, redirect_url, keyword_color, faq_id))
        conn.commit()
        conn.close()
        flash('Pergunta atualizada com sucesso.', 'success')
        return redirect(url_for('admin_faqs'))

    try:
        conn = get_db()
        
        # MIGRATIONS: Remove FAQs repetidas e adiciona coluna de cor
        try: conn.execute("ALTER TABLE faqs ADD COLUMN keyword_color TEXT DEFAULT '#eab308'")
        except: pass
        
        try: conn.execute("DELETE FROM faqs WHERE id NOT IN (SELECT MIN(id) FROM faqs GROUP BY question, answer)")
        except: pass
        
        conn.commit()
        
        # Só cria os usuários padrão se ainda não existirem — sem UPDATE no startup
        dev_exists = conn.execute('SELECT id FROM users WHERE email = ?', ('desenvolper@fkn.com',)).fetchone()
        if not dev_exists:
            conn.execute('INSERT INTO users (email, password_hash, name, role) VALUES (?, ?, ?, ?)',
                         ('desenvolper@fkn.com', generate_password_hash('Praxair1'), 'Desenvolvedor Master', 'developer'))
            conn.commit()

        master_exists = conn.execute('SELECT id FROM users WHERE email = ?', ('admin@admin.com',)).fetchone()
        if not master_exists:
            conn.execute('INSERT INTO users (email, password_hash, name, role) VALUES (?, ?, ?, ?)',
                         ('admin@admin.com', generate_password_hash('123456'), 'Professor', 'master'))
            conn.commit()

        conn.close()
    except Exception as e:
        print(f"[startup] Aviso: {e}")
        try: conn.rollback()
        except: pass
        try: conn.close()
        except: pass

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
    conn = get_db()
    
    if file and file.filename != '' and allowed_file(file.filename):
        filename = f"bug_{int(time.time())}_{secure_filename(file.filename)}"
        if supabase:
            file_content = file.read()
            content_type = file.content_type or 'application/octet-stream'
            uploaded_url = supabase_upload('materiais', f"bugs/{filename}", file_content, content_type)
            if uploaded_url:
                filename = uploaded_url
            else:
                file.seek(0)
                os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], 'bugs'), exist_ok=True)
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], 'bugs', filename))
        else:
            os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], 'bugs'), exist_ok=True)
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], 'bugs', filename))
    
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
    return redirect(url_for('view_reports'))

@app.route('/admin/dev_panel', methods=['GET', 'POST'])
def dev_panel():
    if session.get('role') != 'developer': 
        flash('Acesso restrito ao Desenvolvedor Master.', 'error')
        return redirect(url_for('admin'))
    
    conn = get_db()
    if request.method == 'POST':
        keys = ['dev_instagram_url', 'dev_name', 'show_dev_name', 'x_url', 'facebook_url', 'whatsapp_url', 'footer_rights', 'home_hero_title', 'home_hero_subtitle', 'site_name', 'primary_color']
        for k in keys:
            val = request.form.get(k, '')
            conn.execute('INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=EXCLUDED.value', (k, val))
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
        keyword_color = request.form.get('keyword_color', '#eab308')
        conn.execute('INSERT INTO faqs (question, answer, keyword, redirect_url, keyword_color) VALUES (?, ?, ?, ?, ?)', (question, answer, keyword, redirect_url, keyword_color))
        conn.commit()
        flash('FAQ Adicionada!', 'success')
    
    faqs = conn.execute('SELECT * FROM faqs ORDER BY order_num ASC').fetchall()
    conn.close()
    return render_template('admin_faqs.html', faqs=faqs)

# Sistema de Simulados Desativado por Solicitação do Usuário

if __name__ == '__main__': app.run(debug=True, port=5000)
