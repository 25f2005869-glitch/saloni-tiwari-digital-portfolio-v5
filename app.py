import os, re, secrets, mimetypes, time, io
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse
from functools import wraps

from flask import Flask, render_template, request, redirect, url_for, session, flash, abort, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import select, func
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename
from dotenv import load_dotenv
from PIL import Image, UnidentifiedImageError

BASE_DIR = Path(__file__).resolve().parent

# Load local secrets from .env; real environment variables take precedence.
load_dotenv(BASE_DIR / '.env')

DATA_DIR = Path(os.getenv('DATA_DIR', BASE_DIR / 'instance')).resolve()
UPLOAD_DIR = Path(os.getenv('UPLOAD_DIR', DATA_DIR / 'uploads')).resolve()
DATA_DIR.mkdir(parents=True, exist_ok=True)
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

app = Flask(__name__)
app.config.update(
    SECRET_KEY=os.getenv('SECRET_KEY') or os.getenv('FLASK_SECRET_KEY') or secrets.token_hex(32),
    SQLALCHEMY_DATABASE_URI=(os.getenv('DATABASE_URL', f"sqlite:///{(DATA_DIR / 'portfolio.db').as_posix()}").replace('postgres://', 'postgresql+psycopg://', 1).replace('postgresql://', 'postgresql+psycopg://', 1) if os.getenv('DATABASE_URL') else f"sqlite:///{(DATA_DIR / 'portfolio.db').as_posix()}"),
    SQLALCHEMY_TRACK_MODIFICATIONS=False,
    MAX_CONTENT_LENGTH=20 * 1024 * 1024,
    UPLOAD_FOLDER=str(UPLOAD_DIR),
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Lax',
    SESSION_COOKIE_SECURE=os.getenv('COOKIE_SECURE', '0') == '1',
    PERMANENT_SESSION_LIFETIME=60 * 60 * 8,
)
if os.getenv('FLASK_ENV') == 'production' and not (os.getenv('SECRET_KEY') or os.getenv('FLASK_SECRET_KEY')):
    raise RuntimeError('Set SECRET_KEY (or FLASK_SECRET_KEY) in production before starting the app.')

db = SQLAlchemy(app)

COLLECTIONS = {
 'projects': {'label':'Projects','fields':[('title','Title','text',True),('category','Category','text',False),('description','Short description','textarea',False),('tools','Tools / technologies (comma separated)','text',False),('github_url','GitHub repository URL','url',False),('demo_url','Live demo URL','url',False),('file','Thumbnail / project image','file',False)]},
 'certificates': {'label':'Certificates','fields':[('title','Certificate name','text',True),('organization','Organization / institution','text',False),('category','Category','text',False),('issue_date','Issue date','date',False),('skills','Skills covered','text',False),('credential_url','Credential / verification URL','url',False),('credential_id','Credential ID','text',False),('description','Short description','textarea',False),('file','Certificate image / PDF','file',False)]},
 'education': {'label':'Education','fields':[('title','Degree / course','text',True),('institution','Institution / university','text',False),('level','Level','text',False),('start_date','Start date','date',False),('end_date','End date','date',False),('status','Status','text',False),('details','Details','textarea',False),('file','Marksheet / document','file',False)]},
 'achievements': {'label':'Achievements','fields':[('title','Achievement title','text',True),('organization','Platform / organization','text',False),('date','Date','date',False),('metric','Rating / rank / statistics','text',False),('url','Proof / profile URL','url',False),('description','Description','textarea',False),('file','Badge / image','file',False)]},
 'skills': {'label':'Skills','fields':[('title','Skill','text',True),('category','Category','text',False),('level','Level','text',False),('details','Details','textarea',False)]},
 'journey': {'label':'Learning Journey','fields':[('title','Course / milestone','text',True),('category','Category','text',False),('status','Status','text',False),('date','Date','date',False),('details','Details','textarea',False),('url','Related URL','url',False)]},
 'media': {'label':'Media Gallery','fields':[('title','Title','text',True),('category','Type / category','text',False),('description','Description','textarea',False),('url','External media URL','url',False),('file','Image / video / PDF','file',False)]},
 'profiles': {'label':'Social & Coding Profiles','fields':[('platform','Platform name','text',True),('url','Profile URL','url',True),('handle','Username / handle','text',False),('stats','Stats (rating, solved count, followers, etc.)','text',False),('description','Description','textarea',False),('extra_info','Additional custom details','textarea',False),('file','Badge / screenshot','file',False)]},
}
ALLOWED_EXT = {'png','jpg','jpeg','webp','gif','pdf','mp4','webm'}

class Entry(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    collection = db.Column(db.String(30), nullable=False, index=True)
    title = db.Column(db.String(220), nullable=False, default='')
    payload = db.Column(db.JSON, nullable=False, default=dict)
    file_name = db.Column(db.String(255))
    published = db.Column(db.Boolean, nullable=False, default=True)
    sort_order = db.Column(db.Integer, nullable=False, default=0)
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

class Setting(db.Model):
    key = db.Column(db.String(80), primary_key=True)
    value = db.Column(db.Text, nullable=False, default='')

class LoginAttempt(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    ip = db.Column(db.String(64), nullable=False, index=True)
    created_at = db.Column(db.Float, nullable=False, default=time.time)

with app.app_context():
    db.create_all()
    for k,v in {'name':'Saloni Tiwari','headline':'Student | Data Science & Applications','intro':'Welcome to my digital portfolio. I am documenting my learning journey, projects and achievements.','email':'','location':'India','profile_image':'/static/assets/profile.webp'}.items():
        if not db.session.get(Setting,k): db.session.add(Setting(key=k,value=v))
    db.session.commit()


def setting(key, default=''):
    row=db.session.get(Setting,key)
    return row.value if row else default

def all_settings():
    return {x.key:x.value for x in db.session.scalars(select(Setting)).all()}

@app.context_processor
def inject_template_settings():
    # Make profile settings available to every template, including login,
    # dashboard and manager pages that extend base.html.
    return {'settings': all_settings()}

def csrf_token():
    if '_csrf' not in session: session['_csrf']=secrets.token_urlsafe(32)
    return session['_csrf']
app.jinja_env.globals['csrf_token']=csrf_token
app.jinja_env.globals['collections']=COLLECTIONS

@app.before_request
def security_checks():
    if request.method == 'POST':
        token=request.form.get('_csrf','')
        if not token or not secrets.compare_digest(token, session.get('_csrf','')):
            abort(400, 'Invalid or expired form token. Refresh and try again.')

@app.after_request
def security_headers(response):
    response.headers['X-Content-Type-Options']='nosniff'
    response.headers['X-Frame-Options']='DENY'
    response.headers['Referrer-Policy']='strict-origin-when-cross-origin'
    response.headers['Permissions-Policy']='camera=(), microphone=(), geolocation=()'
    response.headers['Content-Security-Policy']="default-src 'self'; img-src 'self' data: https:; style-src 'self' 'unsafe-inline'; script-src 'self'; font-src 'self' data:; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
    if request.is_secure: response.headers['Strict-Transport-Security']='max-age=31536000; includeSubDomains'
    return response

def admin_required(fn):
    @wraps(fn)
    def wrapped(*args,**kwargs):
        if not session.get('admin'): return redirect(url_for('login'))
        return fn(*args,**kwargs)
    return wrapped

def safe_url(value):
    if not value: return ''
    p=urlparse(value.strip())
    return value.strip() if p.scheme in ('http','https') and p.netloc else ''

def save_upload(file):
    """Validate and save an upload. Raster images are resized and converted to WebP."""
    if not file or not file.filename:
        return None

    original = secure_filename(file.filename)
    ext = original.rsplit('.', 1)[-1].lower() if '.' in original else ''
    if ext not in ALLOWED_EXT:
        raise ValueError('Unsupported file type. Allowed: PNG, JPG, WEBP, GIF, PDF, MP4, WEBM.')

    raw = file.read()
    if not raw:
        raise ValueError('The selected file is empty.')
    if len(raw) > app.config['MAX_CONTENT_LENGTH']:
        raise ValueError('File is too large. Maximum upload size is 20 MB.')

    # Convert static raster images to optimized WebP; retain animated GIFs and documents/videos.
    if ext in {'png', 'jpg', 'jpeg', 'webp'}:
        try:
            with Image.open(io.BytesIO(raw)) as source:
                source.verify()
            with Image.open(io.BytesIO(raw)) as source:
                source = source.convert('RGBA' if 'A' in source.getbands() else 'RGB')
                source.thumbnail((1600, 1600), Image.Resampling.LANCZOS)
                name = f"{secrets.token_hex(16)}.webp"
                target = UPLOAD_DIR / name
                source.save(target, format='WEBP', quality=82, method=6)
        except (UnidentifiedImageError, OSError, ValueError):
            raise ValueError('The selected image is invalid or corrupted.')
        return name

    if ext == 'gif':
        try:
            with Image.open(io.BytesIO(raw)) as source:
                if source.format != 'GIF':
                    raise ValueError('The selected GIF file is invalid.')
                source.verify()
        except (UnidentifiedImageError, OSError):
            raise ValueError('The selected GIF file is invalid or corrupted.')
        final_ext = 'gif'
    elif ext == 'pdf':
        if not raw.startswith(b'%PDF-'):
            raise ValueError('The selected PDF file is invalid.')
        final_ext = 'pdf'
    elif ext == 'mp4':
        if len(raw) < 12 or raw[4:8] != b'ftyp':
            raise ValueError('The selected MP4 file is invalid.')
        final_ext = 'mp4'
    else:  # webm
        if not raw.startswith(b'\x1a\x45\xdf\xa3'):
            raise ValueError('The selected WebM file is invalid.')
        final_ext = 'webm'

    name = f"{secrets.token_hex(16)}.{final_ext}"
    (UPLOAD_DIR / name).write_bytes(raw)
    return name


def remove_upload_if_unused(filename):
    """Remove an upload only when no profile setting or entry still references it."""
    if not filename:
        return
    if setting('profile_image', '') == f'/uploads/{filename}':
        return
    entries = db.session.scalars(select(Entry)).all()
    if any((entry.payload or {}).get('file') == filename for entry in entries):
        return
    try:
        (UPLOAD_DIR / filename).unlink(missing_ok=True)
    except OSError:
        app.logger.exception("Could not remove obsolete upload %s", filename)

def public_entries(collection):
    return db.session.scalars(select(Entry).where(Entry.collection==collection,Entry.published.is_(True)).order_by(Entry.sort_order,Entry.id.desc())).all()

@app.route('/')
def home():
    data={k:public_entries(k) for k in COLLECTIONS}
    return render_template('home.html', data=data)

@app.route('/uploads/<path:filename>')
def uploaded_file(filename):
    # Random filenames; public files are only served when linked to a published entry.
    entries=db.session.scalars(select(Entry).where(Entry.published.is_(True))).all()
    entry=next((e for e in entries if (e.payload or {}).get('file') == filename), None)
    profile_path=setting('profile_image','')
    if not entry and profile_path != f'/uploads/{filename}': abort(404)
    return send_from_directory(UPLOAD_DIR,filename,as_attachment=False,conditional=True)

@app.route('/login',methods=['GET','POST'])
def login():
    if session.get('admin'): return redirect(url_for('dashboard'))
    if request.method=='POST':
        ip=request.headers.get('X-Forwarded-For',request.remote_addr or 'unknown').split(',')[0].strip()
        cutoff=time.time()-900
        db.session.execute(LoginAttempt.__table__.delete().where(LoginAttempt.created_at <= cutoff))
        db.session.commit()
        recent=db.session.scalars(select(LoginAttempt).where(LoginAttempt.ip==ip,LoginAttempt.created_at>cutoff)).all()
        if len(recent)>=8:
            flash('Too many attempts. Please wait 15 minutes.','error')
            return render_template('login.html'),429
        db.session.add(LoginAttempt(ip=ip)); db.session.commit()
        password=os.getenv('ADMIN_PASSWORD','')
        username=os.getenv('ADMIN_USERNAME','saloni')
        if password and secrets.compare_digest(request.form.get('username',''),username) and secrets.compare_digest(password,request.form.get('password','')):
            session.clear(); session['admin']=True; session.permanent=True
            return redirect(url_for('dashboard'))
        flash('Invalid username or password.','error')
    return render_template('login.html')

@app.route('/logout',methods=['POST'])
@admin_required
def logout():
    session.clear(); flash('You have been logged out.','success'); return redirect(url_for('home'))

@app.route('/admin')
@admin_required
def dashboard():
    counts={k:db.session.scalar(select(func.count(Entry.id)).where(Entry.collection==k)) or 0 for k in COLLECTIONS}
    return render_template('dashboard.html',counts=counts)

@app.route('/admin/settings',methods=['GET','POST'])
@admin_required
def settings():
    if request.method=='POST':
        for key in ('name','headline','intro','email','location'):
            row=db.session.get(Setting,key)
            if row: row.value=request.form.get(key,'').strip()
        f=request.files.get('profile_image')
        if f and f.filename:
            old_path = setting('profile_image', '')
            name = save_upload(f)
            row = db.session.get(Setting, 'profile_image')
            row.value = f'/uploads/{name}'
            db.session.commit()
            if old_path.startswith('/uploads/'):
                remove_upload_if_unused(old_path.rsplit('/', 1)[-1])
        else:
            db.session.commit()
        flash('Profile settings saved.','success'); return redirect(url_for('settings'))
    return render_template('settings.html')

@app.route('/admin/<collection>')
@admin_required
def manage(collection):
    if collection not in COLLECTIONS: abort(404)
    entries=db.session.scalars(select(Entry).where(Entry.collection==collection).order_by(Entry.id.desc())).all()
    return render_template('manage.html',collection=collection,config=COLLECTIONS[collection],entries=entries)

@app.route('/admin/<collection>/save',methods=['POST'])
@admin_required
def save_entry(collection):
    if collection not in COLLECTIONS: abort(404)
    raw_id=request.form.get('id','').strip(); entry=db.session.get(Entry,int(raw_id)) if raw_id.isdigit() else None
    if entry and entry.collection!=collection: abort(404)
    payload=dict(entry.payload or {}) if entry else {}
    old_filename = payload.get('file')
    for key,label,kind,required in COLLECTIONS[collection]['fields']:
        if kind=='file':
            f=request.files.get(key)
            if f and f.filename: payload[key]=save_upload(f)
        else:
            val=request.form.get(key,'').strip()
            if kind=='url' and val:
                val=safe_url(val)
                if not val: raise ValueError(f'{label} must be a valid http/https URL.')
            if required and not val: raise ValueError(f'{label} is required.')
            payload[key]=val
    title=payload.get('title') or payload.get('platform') or 'Untitled'
    if entry:
        entry.title=title; entry.payload=payload; entry.published=request.form.get('published')=='on'
    else:
        entry=Entry(collection=collection,title=title,payload=payload,published=request.form.get('published')=='on')
        db.session.add(entry)
    db.session.commit()
    if old_filename and payload.get('file') != old_filename:
        remove_upload_if_unused(old_filename)
    flash('Entry saved.','success'); return redirect(url_for('manage',collection=collection))

@app.route('/admin/<collection>/<int:entry_id>/edit')
@admin_required
def edit_entry(collection,entry_id):
    if collection not in COLLECTIONS: abort(404)
    entry=db.session.get(Entry,entry_id)
    if not entry or entry.collection!=collection: abort(404)
    return render_template('manage.html',collection=collection,config=COLLECTIONS[collection],entries=db.session.scalars(select(Entry).where(Entry.collection==collection).order_by(Entry.id.desc())).all(),editing=entry)

@app.route('/admin/<collection>/<int:entry_id>/delete',methods=['POST'])
@admin_required
def delete_entry(collection,entry_id):
    if collection not in COLLECTIONS: abort(404)
    entry=db.session.get(Entry,entry_id)
    if not entry or entry.collection!=collection: abort(404)
    filename = (entry.payload or {}).get('file') or entry.file_name
    db.session.delete(entry)
    db.session.commit()
    remove_upload_if_unused(filename)
    flash('Entry deleted.','success'); return redirect(url_for('manage',collection=collection))

@app.route('/health')
def health():
    try: db.session.execute(select(1)); return {'status':'ok','database':'connected'},200
    except Exception: return {'status':'error','database':'unavailable'},503

@app.errorhandler(ValueError)
def value_error(err):
    db.session.rollback(); flash(str(err),'error')
    return redirect(request.referrer or url_for('dashboard'))

@app.errorhandler(413)
def too_large(_):
    flash('File is too large. Maximum upload size is 20 MB.','error')
    return redirect(request.referrer or url_for('dashboard'))

if __name__=='__main__': app.run(host='127.0.0.1',port=5000,debug=True)
