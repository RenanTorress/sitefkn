from flask import Flask, render_template, request, redirect, url_for, session, send_from_directory, flash, g
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import os
import sqlite3
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
            session['profile_pic'] = user['profile_pic']
            return redirect(url_for('admin'))
        else:
            flash('Login inválido', 'error')
            
    return render_template('login.html')

@app.route('/logout')
def logout():
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
    except sqlite3.OperationalError:
        topicos_pendentes = [] # Tratamento em caso do banco ainda não migrado
        topicos_respondidos = []
        
    conn.close()
    return render_template('admin.html', users=users, all_folders=all_folders, forums=forums, files=files, topicos_pendentes=topicos_pendentes, topicos_respondidos=topicos_respondidos)

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
    flash('Seu perfil foi atualizado com sucesso!', 'success')
    return redirect(url_for('admin'))

@app.route('/admin/remove_banner', methods=['POST'])
def remove_banner():
    if 'user_id' not in session: return redirect(url_for('login'))
    conn = get_db()
    conn.execute("DELETE FROM settings WHERE key = 'home_image_url'")
    conn.commit()
    conn.close()
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
    flash('Configurações atualizadas para o site!', 'success')
    return redirect(url_for('admin'))

@app.route('/admin/add_user', methods=['POST'])
def add_user():
    if 'user_id' not in session: return redirect(url_for('login'))
    name = request.form.get('name', 'Professor Auxiliar')
    email = request.form['email']
    password = request.form['password']
    conn = get_db()
    try:
        conn.execute('INSERT INTO users (email, password_hash, name) VALUES (?, ?, ?)',
                     (email, generate_password_hash(password), name))
        conn.commit()
        flash('Admin adicionado!', 'success')
    except sqlite3.IntegrityError:
        flash('Email já existe.', 'error')
    finally:
        conn.close()
    return redirect(url_for('admin'))

@app.route('/admin/delete_user/<int:user_id>', methods=['POST'])
def delete_user(user_id):
    if session.get('email') != 'admin@admin.com':
        flash('Somente o master pode exluir contas.', 'error')
        return redirect(url_for('admin'))
        
    conn = get_db()
    target = conn.execute('SELECT email FROM users WHERE id = ?', (user_id,)).fetchone()
    if target and target['email'] != 'admin@admin.com':
        conn.execute('DELETE FROM users WHERE id = ?', (user_id,))
        conn.commit()
        flash('Conta de administrador excluída.', 'success')
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
        flash('Sala de Fórum criada!', 'success')
    return redirect(url_for('admin'))

@app.route('/admin/delete_forum/<int:forum_id>', methods=['POST'])
def delete_forum(forum_id):
    if 'user_id' not in session: return redirect(url_for('login'))
    conn = get_db()
    conn.execute('DELETE FROM forums WHERE id = ?', (forum_id,))
    conn.commit()
    conn.close()
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
        return redirect(url_for('view_topic', topic_id=topic_id))
        
    try:
        messages = conn.execute('''
            SELECT m1.*, m2.content as reply_to_content, m2.author_name as reply_to_author, 
                   u.profile_pic as admin_pic, u.name as admin_name
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
        flash('PDF removido com sucesso!', 'success')
    conn.close()
    return redirect(url_for('admin'))

@app.route('/download/<int:file_id>')
def download(file_id):
    conn = get_db()
    file_record = conn.execute('SELECT * FROM files WHERE id = ?', (file_id,)).fetchone()
    conn.close()
    if file_record:
        return send_from_directory(app.config['UPLOAD_FOLDER'], file_record['filepath'], as_attachment=True, download_name=file_record['filename'])
    return 'Arquivo nulo', 404
    
@app.route('/download_forum/<filename>')
def download_forum(filename): return send_from_directory(os.path.join(app.config['UPLOAD_FOLDER'], 'forum'), secure_filename(filename), as_attachment=True)

with app.app_context():
    init_db()  # Ensure schema exists
    conn = get_db()
    if not conn.execute('SELECT id FROM users').fetchone():
        conn.execute('INSERT INTO users (email, password_hash, name) VALUES (?, ?, ?)',
                     ('admin@admin.com', generate_password_hash('123456'), 'Fundador Oficial'))
        conn.commit()
    conn.close()

if __name__ == '__main__': app.run(debug=True, port=5000)
