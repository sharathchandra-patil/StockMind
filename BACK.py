from flask import Flask, request, jsonify, render_template, redirect, url_for, flash, make_response
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
import jwt
import datetime
from functools import wraps
import requests 
import yfinance as yf 
import wikipedia 
from google import genai 
import os
import secrets
import re

from alert_system.scheduler import start_scheduler, alerts
@app.route('/alert_form')
def alert_form():
    return render_template('alert_form.html')
@app.route('/alerts')

@app.route('/create_alert', methods=['POST'])
def create_alert():
    data = request.form
    alerts.append({
        'type': data.get('type'),             # "price" or "rsi"
        'ticker': data.get('ticker'),
        'target': float(data.get('target', 0)),
        'threshold': float(data.get('threshold', 30)),
        'direction': data.get('direction'),
        'email': data.get('email')
    })
    flash(f"Alert created for {data.get('ticker')}", "success")
    return redirect('/')

start_scheduler()

# Initialize Flask extensions
db = SQLAlchemy()
login_manager = LoginManager()
EMAIL_REGEX = re.compile(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$')

# Load API keys 
GEMINI_API_KEY = "your_gemini_apikey"  # GeminiAPIKey 
ALPHA_VANTAGE_API_KEY = "your_alpha_vantage_apikey"  # AlphaVantageAPIKey 
client = genai.Client(api_key=GEMINI_API_KEY)

app = Flask(__name__, static_folder="static", template_folder="templates")

# Configuration
app.config['SECRET_KEY'] = secrets.token_hex(32)  # Change this in production!
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///stockmind.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['JWT_SECRET_KEY'] = secrets.token_hex(32)  # For API tokens

# Initialize extensions
db.init_app(app)
login_manager.init_app(app)
login_manager.login_view = 'login'


def validate_email(email):
    return bool(EMAIL_REGEX.match(email))

def validate_password(password):
    return len(password) >= 8

def validate_username(username):
    return len(username) >= 3


# User model
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(128))

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# JWT token required decorator for API routes
def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None
        
        if 'Authorization' in request.headers:
            token = request.headers['Authorization'].split(" ")[1]
            
        if not token:
            return jsonify({'message': 'Token is missing!'}), 401
            
        try:
            data = jwt.decode(token, app.config['JWT_SECRET_KEY'], algorithms=["HS256"])
            current_user = User.query.filter_by(id=data['user_id']).first()
        except:
            return jsonify({'message': 'Token is invalid!'}), 401
            
        return f(current_user, *args, **kwargs)
        
    return decorated


def fetch_wikipedia_summary(company_name): 
    print(f"\n🔍 ==== Fetching Wikipedia summary for {company_name} ====")
    try: 
        search_results = wikipedia.search(company_name) 
        if search_results: 
            page_title = search_results[0] 
            summary = wikipedia.summary(page_title, sentences=2) 
            print(f"✅ Summary found for: {page_title}.")
            return page_title, summary 
    except Exception as e: 
        print(f"❌ Error fetching Wikipedia summary: {str(e)}")
        return None, f"Error fetching Wikipedia summary: {str(e)}" 
    print("⚠️ No Wikipedia page found for the given company.")
    return None, "No Wikipedia page found for the given company." 

 
def fetch_stock_price(ticker): 
    print(f"\n📈 ==== Fetching 3-month stock prices for {ticker} ====")
    try: 
        stock = yf.Ticker(ticker) 
        history = stock.history(period="3mo") 
        time_labels = history.index.strftime('%Y-%m-%d').tolist() 
        stock_prices = [round(price, 2) for price in history['Close'].tolist()]  
        print(f"✅ Successfully fetched stock prices for {ticker}.")
        return stock_prices, time_labels 
    except Exception as e: 
        print(f"❌ Error fetching stock price: {str(e)}")
        return None, None


 
def get_ticker_from_alpha_vantage(company_name): 
    print(f"\n🔎 ==== Searching Alpha Vantage for ticker: {company_name} ====")
    try: 
        url = "https://www.alphavantage.co/query" 
        params = { 
            "function": "SYMBOL_SEARCH", 
            "keywords": company_name, 
            "apikey": ALPHA_VANTAGE_API_KEY, 
        } 
        response = requests.get(url, params=params) 
        data = response.json() 
        if "bestMatches" in data: 
            for match in data["bestMatches"]: 
                if match["4. region"] == "United States": 
                    print(f"✅ Found ticker: {match['1. symbol']}")
                    return match["1. symbol"] 
        print("⚠️ No suitable ticker found.")
        return None 
    except Exception as e: 
        print(f"❌ Error fetching ticker: {str(e)}")
        return None 

 
def fetch_market_cap(ticker): 
    print(f"\n💰 ==== Fetching market cap for {ticker} ====")
    try: 
        stock = yf.Ticker(ticker) 
        market_cap = stock.info.get('marketCap', None) 
        if market_cap:
            print(f"✅ Market cap: {market_cap}")
        else:
            print("⚠️ Market cap not available.")
        return market_cap 
    except Exception as e: 
        print(f"❌ Error fetching market cap: {str(e)}")
        return None 

 
def get_top_competitors(competitors): 
    print("\n👥 ==== Processing Top Competitors ====")
    competitor_data = [] 
    processed_tickers = set()  
 
    for competitor in set(competitors):  
        print(f"\n➡️ Processing competitor: {competitor}")
        ticker = get_ticker_from_alpha_vantage(competitor) 
        if ticker and ticker not in processed_tickers: 
            market_cap = fetch_market_cap(ticker) 
            stock_prices, time_labels = get_stock_price_for_competitor(ticker) 
            if market_cap and stock_prices and time_labels: 
                competitor_data.append({ 
                    "name": competitor, 
                    "ticker": ticker, 
                    "market_cap": market_cap, 
                    "stock_prices": stock_prices, 
                    "time_labels": time_labels, 
                    "stock_price": stock_prices[-1], 
                }) 
                processed_tickers.add(ticker)  
                print(f"✅ Added {competitor} ({ticker}) to top competitors.")
            else:
                print(f"⚠️ Incomplete data for {competitor}. Skipping.")
 
    top_competitors = sorted(competitor_data, key=lambda x: x["market_cap"], reverse=True)[:3] 
    print("🏆 Top competitors selected based on market cap.")
    return top_competitors 

 

 
def query_gemini_llm(description): 
    print("\n🤖 ==== Querying Gemini for sector and competitor info ====")
    try: 
        prompt = f""" 
        Provide a structured list of sectors and their competitors for the following company description: 
        {description[:500]} 
        Format: 
        Sector Name : 
            Competitor 1 
            Competitor 2 
            Competitor 3 
 
        Leave a line after each sector. Do not use bullet points. 
        """ 
        response = client.models.generate_content( 
            model="gemini-1.5-flash", contents=prompt 
        ) 
        content = response.candidates[0].content.parts[0].text 
        sectors = [] 
        for line in content.split("\n\n"): 
            lines = line.strip().split("\n") 
            if len(lines) > 1: 
                sector_name = lines[0].strip() 
                competitors = [l.strip() for l in lines[1:]] 
                sectors.append({"name": sector_name, "competitors": competitors}) 
        print("✅ Gemini response parsed successfully.")
        return sectors 
    except Exception as e: 
        print(f"❌ Error querying Gemini: {str(e)}")
        return None 

 
# Authentication routes
@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('home'))

    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        
        # Basic validation
        if not email or not password:
            flash('Please fill in all fields', 'error')
            return redirect(url_for('login'))
            
        if not validate_email(email):
            flash('Please enter a valid email address', 'error')
            return redirect(url_for('login'))
            
        user = User.query.filter_by(email=email).first()
        
        if user is None or not user.check_password(password):
            flash('Invalid email or password', 'error')
            return redirect(url_for('login'))
            
        login_user(user)
        flash('Logged in successfully!', 'success')
        next_page = request.args.get('next')
        return redirect(next_page or url_for('home'))
    
    return render_template('login.html')


@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('home'))
        
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        
        # Server-side validation
        if not validate_username(username):
            flash('Username must be at least 3 characters', 'error')
            return redirect(url_for('register'))
            
        if not validate_email(email):
            flash('Please enter a valid email address', 'error')
            return redirect(url_for('register'))
            
        if not validate_password(password):
            flash('Password must be at least 8 characters long', 'error')
            return redirect(url_for('register'))
            
        if User.query.filter_by(email=email).first():
            flash('Email already exists', 'error')
            return redirect(url_for('register'))
            
        if User.query.filter_by(username=username).first():
            flash('Username already taken', 'error')
            return redirect(url_for('register'))
            
        user = User(username=username, email=email)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        
        flash('Registration successful! Please log in.', 'success')
        return redirect(url_for('login'))
    
    return render_template('register.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Logout successful!')  # Simple success message
    return redirect(url_for('login'))
# API Authentication routes
@app.route('/api/auth/signup', methods=['POST'])
def api_signup():
    data = request.get_json()
    
    # Validate input
    if not data.get('email') or not data.get('password'):
        return jsonify({'message': 'Email and password are required'}), 400
    
    if not validate_email(data['email']):
        return jsonify({'message': 'Please enter a valid email address'}), 400
        
    if not validate_password(data['password']):
        return jsonify({'message': 'Password must be at least 8 characters'}), 400
    
    if User.query.filter_by(email=data['email']).first():
        return jsonify({'message': 'Email already exists'}), 400
    
    username = data.get('fullname', data['email'].split('@')[0])
    if User.query.filter_by(username=username).first():
        return jsonify({'message': 'Username already taken'}), 400
    
    user = User(username=username, email=data['email'])
    user.set_password(data['password'])
    
    db.session.add(user)
    db.session.commit()
    
    token = jwt.encode({
        'user_id': user.id,
        'exp': datetime.datetime.utcnow() + datetime.timedelta(days=30)
    }, app.config['JWT_SECRET_KEY'])
    
    return jsonify({
        'token': token,
        'userId': user.id,
        'email': user.email
    })
@app.route('/api/auth/login', methods=['POST'])
def api_login():
    data = request.get_json()
    
    # Validate input
    if not data.get('email') or not data.get('password'):
        return jsonify({'message': 'Email and password are required'}), 400
    
    if not validate_email(data['email']):
        return jsonify({'message': 'Please enter a valid email address'}), 400
    
    user = User.query.filter_by(email=data['email']).first()
    
    if not user or not user.check_password(data['password']):
        return jsonify({'message': 'Invalid credentials'}), 401
    
    token = jwt.encode({
        'user_id': user.id,
        'exp': datetime.datetime.utcnow() + datetime.timedelta(days=30)
    }, app.config['JWT_SECRET_KEY'])
    
    return jsonify({
        'token': token,
        'userId': user.id,
        'email': user.email
    })
# Protect existing routes
@app.route("/")
def home():
    return render_template("FRONT.html")

@app.route("/analyze_company", methods=["GET"])
@login_required
def analyze_company():
    company_name = request.args.get("company_name")
    if not company_name:
        return jsonify(success=False, error="No company name provided.")

    _, summary = fetch_wikipedia_summary(company_name)
    if not summary:
        return jsonify(success=False, error="Could not find company description.")

    ticker = get_ticker_from_alpha_vantage(company_name)
    if not ticker:
        return jsonify(success=False, error="Could not find ticker symbol.")

    stock_prices, time_labels = fetch_stock_price(ticker)
    if not stock_prices or not time_labels:
        return jsonify(success=False, error="Could not fetch stock prices.")

    competitors = query_gemini_llm(summary)
    if not competitors:
        competitors = [{"name": "No Sectors", "competitors": ["No competitors found."]}]

    all_competitors = [comp for sector in competitors for comp in sector["competitors"]]
    top_competitors = get_top_competitors(all_competitors)

    return jsonify(
        success=True,
        description=summary,
        ticker=ticker,
        stock_prices=stock_prices,
        time_labels=time_labels,
        competitors=competitors,
        top_competitors=top_competitors,
    )

# Initialize database
with app.app_context():
    db.create_all()

if __name__ == "__main__":
    app.run(debug=True)
