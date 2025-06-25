from flask import Flask, Blueprint, render_template, redirect, url_for, request, session
from authlib.integrations.flask_client import OAuth
from database_model import db, User
from dotenv import load_dotenv
import authenticator
import os
import secrets

# Load environment variables
load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "default_secret")

# Configure OAuth
oauth = OAuth(app)
oauth.register(
    name='google',
    client_id=os.getenv("GOOGLE_CLIENT_ID"),
    client_secret=os.getenv("GOOGLE_CLIENT_SECRET"),
    server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
    client_kwargs={"scope": "openid email profile"},
)
oauth.register(
    name='github',
    client_id=os.getenv("GITHUB_CLIENT_ID"),
    client_secret=os.getenv("GITHUB_CLIENT_SECRET"),
    access_token_url="https://github.com/login/oauth/access_token",
    authorize_url="https://github.com/login/oauth/authorize",
    api_base_url="https://api.github.com/",
    client_kwargs={"scope": "user:email"},
)

# Authentication Blueprint
auth_bp = Blueprint('auth', __name__, url_prefix='/account')

# Traditional Email/Password Login
@auth_bp.route("/login", methods=['POST'])
def login():
    email = request.form['email']
    password = request.form['password']
    if not email or not password:
        return render_template("access-account.html", error="Invalid Information")
    user = User.query.filter_by(email=email).first()
    if user and user.check_password(password):
        session["username"] = user.username
        return redirect(url_for("home"))
    return render_template("access-account.html", error="Invalid Information")

# Traditional Registration
@auth_bp.route("/register", methods=['POST'])
def register():
    username = request.form['username']
    email = request.form['email']
    password = request.form['password']
    if not username or not email or not password:
        return render_template("access-account.html", error="Invalid Information")
    if User.query.filter_by(email=email).first():
        return render_template("access-account.html", error="Account Already Exists")
    new_user = User(username=username, email=email)
    new_user.set_passsword(password)
    session['username'] = username
    session['password'] = new_user.get_passw_hash()
    session['email'] = email
    return redirect(url_for('auth.authenticate'))

# OTP Step
@auth_bp.route('/api/authenticate')
def authenticate():
    username = session['username']
    email = session['email']
    try:
        otp = authenticator.generateOTP(username=username, usermail=email)
        session["otp"] = otp
    except:
        return render_template("access-account.html", error="Invalid email address")
    return render_template("access-account.html", otp=True)

# OTP Verification
@auth_bp.route('/api/verify', methods=['POST'])
def verify():
    inp = request.form['userOTP']
    username = session.pop("username", None)
    password = session.pop("password", None)
    email = session.pop("email", None)
    otp = session.pop("otp", None)
    if authenticator.verifyOTP(otp, inp):
        new_user = User(username=username, email=email, password_hash=password)
        db.session.add(new_user)
        db.session.commit()
        return redirect(url_for('home'))
    return render_template("FRONT.html", error="❌ Invalid OTP")

# Logout
@auth_bp.route('/logout')
def logout():
    session.pop("username", None)
    return redirect(url_for('home'))

# Render Access Page
@auth_bp.route('/access-account')
def accessAccount():
    return render_template("access-account.html")

# Social Login/Register Handlers
@auth_bp.route('/login/google')
def login_google():
    session['register'] = False
    redirect_uri = url_for('auth.google_callback', _external=True)
    return oauth.google.authorize_redirect(redirect_uri)

@auth_bp.route('/register/google')
def register_google():
    session['register'] = True
    redirect_uri = url_for('auth.google_callback', _external=True)
    return oauth.google.authorize_redirect(redirect_uri)

@auth_bp.route('/auth/google/callback')
def google_callback():
    token = oauth.google.authorize_access_token()
    user_info = oauth.google.parse_id_token(token)
    email = user_info.get('email')
    username = user_info.get('name')

    user = User.query.filter_by(email=email).first()
    if not user:
        if session.pop('register', False):
            dummy_password = secrets.token_hex(16)
            user = User(username=username, email=email)
            user.set_passsword(dummy_password)
            db.session.add(user)
            db.session.commit()
        else:
            return render_template("access-account.html", error="⚠️ No account found. Please register first.")

    session['username'] = user.username
    return redirect(url_for('home'))

@auth_bp.route('/login/github')
def login_github():
    session['register'] = False
    redirect_uri = url_for('auth.github_callback', _external=True)
    return oauth.github.authorize_redirect(redirect_uri)

@auth_bp.route('/register/github')
def register_github():
    session['register'] = True
    redirect_uri = url_for('auth.github_callback', _external=True)
    return oauth.github.authorize_redirect(redirect_uri)

@auth_bp.route('/auth/github/callback')
def github_callback():
    token = oauth.github.authorize_access_token()
    user_resp = oauth.github.get('user', token=token)
    user_info = user_resp.json()
    email_resp = oauth.github.get('user/emails', token=token)
    email_data = email_resp.json()
    email = next((e['email'] for e in email_data if e['primary']), None)
    username = user_info.get('login')

    user = User.query.filter_by(email=email).first()
    if not user:
        if session.pop('register', False):
            dummy_password = secrets.token_hex(16)
            user = User(username=username, email=email)
            user.set_passsword(dummy_password)
            db.session.add(user)
            db.session.commit()
        else:
            return render_template("access-account.html", error="⚠️ No account found. Please register first.")

    session['username'] = user.username
    return redirect(url_for('home'))

# Register blueprint
app.register_blueprint(auth_bp)

# Add your existing home route
@app.route('/')
def home():
    username = session.get("username")
    return render_template("home.html", username=username)

if __name__ == '__main__':
    app.run(debug=True)
