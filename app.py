import os, sqlite3
from functools import wraps
from pathlib import Path
from flask import Flask, jsonify, request, session, send_from_directory
import requests
from werkzeug.security import generate_password_hash, check_password_hash

BASE = Path(__file__).resolve().parent
DB = BASE / 'moneytips.db'
API_BASE = 'https://api.football-data.org/v4'
API_KEY = os.getenv('FOOTBALL_DATA_API_KEY', '').strip()
SECRET = os.getenv('FLASK_SECRET_KEY', '').strip()
ADMIN_EMAIL = os.getenv('ADMIN_EMAIL', 'admin@moneytips.app').strip().lower()
ADMIN_PASSWORD = os.getenv('ADMIN_PASSWORD', '').strip()

if not SECRET:
    raise RuntimeError('Defina FLASK_SECRET_KEY antes de iniciar.')
if not API_KEY:
    raise RuntimeError('Defina FOOTBALL_DATA_API_KEY antes de iniciar.')
if not ADMIN_PASSWORD:
    raise RuntimeError('Defina ADMIN_PASSWORD antes de iniciar.')

app = Flask(__name__, static_folder='.', static_url_path='')
app.secret_key = SECRET
app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE='Lax', SESSION_COOKIE_SECURE=os.getenv('COOKIE_SECURE','0')=='1')


def db():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    return con


def init_db():
    con = db()
    con.execute('''CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        email TEXT NOT NULL UNIQUE,
        password_hash TEXT NOT NULL,
        plan TEXT NOT NULL DEFAULT 'free',
        is_admin INTEGER NOT NULL DEFAULT 0,
        status TEXT NOT NULL DEFAULT 'active',
        created TEXT NOT NULL DEFAULT CURRENT_DATE
    )''')
    con.commit()
    row = con.execute('SELECT id FROM users WHERE email=?', (ADMIN_EMAIL,)).fetchone()
    if not row:
        con.execute('INSERT INTO users(name,email,password_hash,plan,is_admin,status) VALUES(?,?,?,?,?,?)',
                     ('Admin', ADMIN_EMAIL, generate_password_hash(ADMIN_PASSWORD), 'vip', 1, 'active'))
        con.commit()
    con.close()


def user_dict(row):
    return {'id': row['id'], 'name': row['name'], 'email': row['email'],
            'plan': row['plan'], 'isAdmin': bool(row['is_admin']), 'status': row['status']}


def current_user():
    uid = session.get('user_id')
    if not uid: return None
    con = db(); row = con.execute('SELECT * FROM users WHERE id=?', (uid,)).fetchone(); con.close()
    if not row or row['status'] != 'active':
        session.clear(); return None
    return row


def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not current_user(): return jsonify(error='Não autenticado.'), 401
        return fn(*args, **kwargs)
    return wrapper


def admin_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        u = current_user()
        if not u: return jsonify(error='Não autenticado.'), 401
        if not u['is_admin']: return jsonify(error='Acesso de administrador negado.'), 403
        return fn(*args, **kwargs)
    return wrapper


@app.get('/')
def index():
    return send_from_directory(BASE, 'index.html')

@app.post('/api/auth/register')
def register():
    data = request.get_json(silent=True) or {}
    name, email, password = str(data.get('name','')).strip(), str(data.get('email','')).strip().lower(), str(data.get('pass',''))
    if len(name) < 2: return jsonify(error='Digite seu nome.'), 400
    if '@' not in email or len(email) > 160: return jsonify(error='E-mail inválido.'), 400
    if len(password) < 6: return jsonify(error='A senha precisa ter pelo menos 6 caracteres.'), 400
    con = db()
    try:
        cur = con.execute('INSERT INTO users(name,email,password_hash) VALUES(?,?,?)', (name,email,generate_password_hash(password)))
        con.commit(); uid = cur.lastrowid
    except sqlite3.IntegrityError:
        con.close(); return jsonify(error='Este e-mail já está cadastrado.'), 409
    row = con.execute('SELECT * FROM users WHERE id=?', (uid,)).fetchone(); con.close()
    session['user_id'] = uid
    return jsonify(user=user_dict(row))

@app.post('/api/auth/login')
def login():
    data = request.get_json(silent=True) or {}
    email, password = str(data.get('email','')).strip().lower(), str(data.get('pass',''))
    con = db(); row = con.execute('SELECT * FROM users WHERE email=?', (email,)).fetchone(); con.close()
    if not row or not check_password_hash(row['password_hash'], password): return jsonify(error='E-mail ou senha incorretos.'), 401
    if row['status'] != 'active': return jsonify(error='Conta desativada. Fale com o admin.'), 403
    session['user_id'] = row['id']
    return jsonify(user=user_dict(row))

@app.get('/api/auth/me')
def me():
    u = current_user()
    return jsonify(user=user_dict(u) if u else None)

@app.post('/api/auth/logout')
def logout():
    session.clear(); return jsonify(ok=True)

@app.get('/api/admin/users')
@admin_required
def admin_users():
    con=db(); rows=con.execute('SELECT id,name,email,plan,is_admin,status,created FROM users ORDER BY id').fetchall(); con.close()
    return jsonify(users=[{'id':r['id'],'name':r['name'],'email':r['email'],'plan':r['plan'],'status':r['status']} for r in rows])

@app.post('/api/admin/plan/<int:user_id>')
@admin_required
def admin_plan(user_id):
    con=db(); row=con.execute('SELECT plan FROM users WHERE id=?',(user_id,)).fetchone()
    if not row: con.close(); return jsonify(error='Usuário não encontrado.'),404
    new='vip' if row['plan']=='free' else 'free'
    con.execute('UPDATE users SET plan=? WHERE id=?',(new,user_id)); con.commit(); con.close()
    return jsonify(ok=True, plan=new)

@app.post('/api/admin/status/<int:user_id>')
@admin_required
def admin_status(user_id):
    con=db(); row=con.execute('SELECT status,is_admin FROM users WHERE id=?',(user_id,)).fetchone()
    if not row: con.close(); return jsonify(error='Usuário não encontrado.'),404
    if row['is_admin']: con.close(); return jsonify(error='A conta de administrador não pode ser desativada por este painel.'),400
    new='cancelled' if row['status']=='active' else 'active'
    con.execute('UPDATE users SET status=? WHERE id=?',(new,user_id)); con.commit(); con.close()
    return jsonify(ok=True, status=new)

@app.get('/api/football/<path:path>')
@login_required
def football_proxy(path):
    # A chave fica somente no servidor; o navegador nunca a recebe.
    url = API_BASE.rstrip('/') + '/' + path.lstrip('/')
    try:
        r = requests.get(url, params=request.args, headers={'X-Auth-Token': API_KEY}, timeout=8)
        return (r.content, r.status_code, {'Content-Type': r.headers.get('Content-Type','application/json'), 'Cache-Control':'no-store'})
    except requests.RequestException:
        return jsonify(error='Falha ao consultar a API de futebol.'), 504

@app.get('/health')
def health():
    return jsonify(ok=True)

init_db()

if __name__ == '__main__':
    app.run(host=os.getenv('HOST','127.0.0.1'), port=int(os.getenv('PORT','5000')), debug=False)
