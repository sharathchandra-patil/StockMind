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
from dotenv import load_dotenv
import traceback

# Load environment variables
load_dotenv()

# Console output styling functions
def print_section(title):
    """Print a section header with consistent formatting"""
    print(f"\n{'=' * 50}")
    print(f"📌 {title.upper()}")
    print(f"{'=' * 50}")

def print_info(message):
    """Print an informational message"""
    print(f"ℹ️ {message}")

def print_success(message):
    """Print a success message"""
    print(f"✅ {message}")

def print_warning(message):
    """Print a warning message"""
    print(f"⚠️ {message}")

def print_error(message):
    """Print an error message"""
    print(f"❌ {message}")

# Initialize Flask extensions
db = SQLAlchemy()
login_manager = LoginManager()
EMAIL_REGEX = re.compile(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$')

# Load API keys 
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY', "your_gemini_apikey")  # GeminiAPIKey 
ALPHA_VANTAGE_API_KEY = os.environ.get('ALPHA_VANTAGE_API_KEY', "your_alpha_vantage_apikey")  # AlphaVantageAPIKey 
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
    print_info(f"🔍 Fetching Wikipedia summary for '{company_name}'...")
    try: 
        search_results = wikipedia.search(company_name) 
        if search_results: 
            page_title = search_results[0] 
            summary = wikipedia.summary(page_title, sentences=2) 
            print_success(f"📚 Found Wikipedia page: '{page_title}'")
            return page_title, summary 
    except Exception as e: 
        print_error(f"📚 Error fetching Wikipedia summary: {str(e)}")
        return None, f"Error fetching Wikipedia summary: {str(e)}" 
    print_warning("📚 No Wikipedia page found for the given company.")
    return None, "No Wikipedia page found for the given company." 
 
def fetch_stock_price(ticker): 
    print_info(f"📈 Fetching stock price history for '{ticker}'...")
    try: 
        # First, verify the ticker is valid by getting basic info
        stock = yf.Ticker(ticker)
        
        # Print the raw response for debugging
        print_info(f"🔍 Attempting to fetch data for {ticker}...")
        
        # Try to get history with a shorter period first
        history = stock.history(period="3mo")
        
        if history.empty:
            print_warning(f"📉 No historical data found for {ticker}. Ticker may be invalid.")
            return None, None
            
        # If that works, try the full period
        history = stock.history(period="3mo")
        
        # Debug info
        print_info(f"📊 Raw data shape: {history.shape}, columns: {list(history.columns)}")
        
        # Check if we have the expected columns
        if 'Close' not in history.columns:
            print_warning(f"📉 Missing 'Close' price data for {ticker}")
            return None, None
            
        # Check if we have a valid index
        if not hasattr(history.index, 'strftime'):
            print_warning(f"📉 Invalid date format in response for {ticker}")
            return None, None
            
        time_labels = history.index.strftime('%Y-%m-%d').tolist()
        stock_prices = [round(price, 2) for price in history['Close'].tolist()]
        
        print_success(f"📊 Successfully retrieved {len(stock_prices)} days of stock price data.")
        return stock_prices, time_labels 
    except Exception as e: 
        print_error(f"📉 Failed to fetch stock prices: {str(e)}")
        # Add more detailed error information
        print_error(f"📉 Error details: {traceback.format_exc()}")
        return None, None

 
def get_ticker_from_alpha_vantage(company_name): 
    print_info(f"🔤 Searching for ticker symbol for '{company_name}'...")
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
                    print_success(f"🏷️ Found ticker symbol: {match['1. symbol']}")
                    return match["1. symbol"] 
        print_warning(f"🔤 No US ticker symbol found for '{company_name}'.")
        return None 
    except Exception as e: 
        print_error(f"🔤 Error searching for ticker: {str(e)}")
        return None 
 
def fetch_market_cap(ticker): 
    print_info(f"💰 Fetching market cap for '{ticker}'...")
    try: 
        stock = yf.Ticker(ticker) 
        market_cap = stock.info.get('marketCap', None) 
        if market_cap:
            print_success(f"💵 Market cap for {ticker}: ${market_cap:,}")
        else:
            print_warning(f"💰 Market cap data not available for {ticker}.")
        return market_cap 
    except Exception as e: 
        print_error(f"💰 Error fetching market cap: {str(e)}")
        return None 
 
def get_stock_price_for_competitor(ticker): 
    print_info(f"🏢 Fetching competitor stock data for '{ticker}'...")
    try: 
        stock = yf.Ticker(ticker) 
        history = stock.history(period="3mo") 
        time_labels = history.index.strftime('%Y-%m-%d').tolist() 
        stock_prices = history['Close'].tolist() 
        print_success(f"📊 Successfully retrieved competitor stock data for {ticker}.")
        return stock_prices, time_labels 
    except Exception as e: 
        print_error(f"📉 Failed to fetch competitor stock data: {str(e)}")
        return None, None 
 
def get_top_competitors(competitors): 
    print_section("🏆 Processing competitors")
    print_info(f"🔍 Analyzing {len(set(competitors))} unique competitors...")
    
    competitor_data = [] 
    processed_tickers = set()  # To track processed tickers and avoid duplicates 
 
    for competitor in set(competitors):  # Remove duplicate names 
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
                processed_tickers.add(ticker)  # Add ticker to the processed set 
 
    # Sort competitors by market cap and return the top 3 
    top_competitors = sorted(competitor_data, key=lambda x: x["market_cap"], reverse=True)[:3] 
    print_success(f"🥇 Found {len(top_competitors)} top competitors by market cap.")
    return top_competitors 
 
def query_gemini_llm(description): 
    print_section("🧠 AI analysis")
    print_info("🤖 Querying Gemini LLM for sector and competitor analysis...")
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
        
        print_success(f"🧩 AI analysis complete. Identified {len(sectors)} sectors.")
        return sectors 
    except Exception as e: 
        print_error(f"🤖 AI analysis failed: {str(e)}")
        return None 
 
# Authentication routes
@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        print_info(f"👤 User already authenticated, redirecting to home")
        return redirect(url_for('home'))

    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        
        print_info(f"🔑 Login attempt for email: {email}")
        
        # Basic validation
        if not email or not password:
            print_warning(f"⚠️ Login failed: Missing email or password")
            flash('Please fill in all fields', 'error')
            return redirect(url_for('login'))
            
        if not validate_email(email):
            print_warning(f"⚠️ Login failed: Invalid email format")
            flash('Please enter a valid email address', 'error')
            return redirect(url_for('login'))
            
        user = User.query.filter_by(email=email).first()
        
        if user is None or not user.check_password(password):
            print_warning(f"⚠️ Login failed: Invalid credentials for {email}")
            flash('Invalid email or password', 'error')
            return redirect(url_for('login'))
            
        login_user(user)
        print_success(f"✅ User logged in successfully: {user.username}")
        flash('Logged in successfully!', 'success')
        next_page = request.args.get('next')
        return redirect(next_page or url_for('home'))
    
    print_info("📝 Rendering login page")
    return render_template('login.html')


@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        print_info(f"👤 User already authenticated, redirecting to home")
        return redirect(url_for('home'))
        
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        
        print_info(f"📝 Registration attempt for username: {username}, email: {email}")
        
        # Server-side validation
        if not validate_username(username):
            print_warning(f"⚠️ Registration failed: Username too short")
            flash('Username must be at least 3 characters', 'error')
            return redirect(url_for('register'))
            
        if not validate_email(email):
            print_warning(f"⚠️ Registration failed: Invalid email format")
            flash('Please enter a valid email address', 'error')
            return redirect(url_for('register'))
            
        if not validate_password(password):
            print_warning(f"⚠️ Registration failed: Password too short")
            flash('Password must be at least 8 characters long', 'error')
            return redirect(url_for('register'))
            
        if User.query.filter_by(email=email).first():
            print_warning(f"⚠️ Registration failed: Email already exists")
            flash('Email already exists', 'error')
            return redirect(url_for('register'))
            
        if User.query.filter_by(username=username).first():
            print_warning(f"⚠️ Registration failed: Username already taken")
            flash('Username already taken', 'error')
            return redirect(url_for('register'))
            
        user = User(username=username, email=email)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        
        print_success(f"✅ User registered successfully: {username}")
        flash('Registration successful! Please log in.', 'success')
        return redirect(url_for('login'))
    
    print_info("📝 Rendering registration page")
    return render_template('register.html')

@app.route('/logout')
@login_required
def logout():
    print_info(f"👋 User {current_user.username} logging out")
    logout_user()
    print_success(f"✅ User logged out successfully")
    flash('Logout successful!')  # Simple success message
    return redirect(url_for('login'))
# API Authentication routes
@app.route('/api/auth/signup', methods=['POST'])
def api_signup():
    data = request.get_json()
    
    print_info(f"🔑 API signup attempt for email: {data.get('email', 'unknown')}")
    
    # Validate input
    if not data.get('email') or not data.get('password'):
        print_warning("⚠️ API signup failed: Missing email or password")
        return jsonify({'message': 'Email and password are required'}), 400
    
    if not validate_email(data['email']):
        print_warning("⚠️ API signup failed: Invalid email format")
        return jsonify({'message': 'Please enter a valid email address'}), 400
        
    if not validate_password(data['password']):
        print_warning("⚠️ API signup failed: Password too short")
        return jsonify({'message': 'Password must be at least 8 characters'}), 400
    
    if User.query.filter_by(email=data['email']).first():
        print_warning("⚠️ API signup failed: Email already exists")
        return jsonify({'message': 'Email already exists'}), 400
    
    username = data.get('fullname', data['email'].split('@')[0])
    if User.query.filter_by(username=username).first():
        print_warning("⚠️ API signup failed: Username already taken")
        return jsonify({'message': 'Username already taken'}), 400
    
    user = User(username=username, email=data['email'])
    user.set_password(data['password'])
    
    db.session.add(user)
    db.session.commit()
    
    token = jwt.encode({
        'user_id': user.id,
        'exp': datetime.datetime.utcnow() + datetime.timedelta(days=30)
    }, app.config['JWT_SECRET_KEY'])
    
    print_success(f"✅ API user registered successfully: {username}")
    return jsonify({
        'token': token,
        'userId': user.id,
        'email': user.email
    })
@app.route('/api/auth/login', methods=['POST'])
def api_login():
    data = request.get_json()
    
    print_info(f"🔑 API login attempt for email: {data.get('email', 'unknown')}")
    
    # Validate input
    if not data.get('email') or not data.get('password'):
        print_warning("⚠️ API login failed: Missing email or password")
        return jsonify({'message': 'Email and password are required'}), 400
    
    if not validate_email(data['email']):
        print_warning("⚠️ API login failed: Invalid email format")
        return jsonify({'message': 'Please enter a valid email address'}), 400
    
    user = User.query.filter_by(email=data['email']).first()
    
    if not user or not user.check_password(data['password']):
        print_warning(f"⚠️ API login failed: Invalid credentials for {data['email']}")
        return jsonify({'message': 'Invalid credentials'}), 401
    
    token = jwt.encode({
        'user_id': user.id,
        'exp': datetime.datetime.utcnow() + datetime.timedelta(days=30)
    }, app.config['JWT_SECRET_KEY'])
    
    print_success(f"✅ API user logged in successfully: {user.username}")
    return jsonify({
        'token': token,
        'userId': user.id,
        'email': user.email
    })
# Protect existing routes
@app.route("/")
def home():
    print_info("🏠 Rendering home page")
    return render_template("FRONT.html")

@app.route("/analyze_company", methods=["GET"])
@login_required
def analyze_company():
    company_name = request.args.get("company_name")
    if not company_name:
        print_warning("⚠️ No company name provided")
        return jsonify(success=False, error="No company name provided.")

    print_section("🔎 Company analysis")
    print_info(f"🚀 Starting analysis for company: '{company_name}'")
 
    _, summary = fetch_wikipedia_summary(company_name) 
    if not summary: 
        print_error("📚 Failed to find company description.")
        return jsonify(success=False, error="Could not find company description.") 
 
    ticker = get_ticker_from_alpha_vantage(company_name) 
    if not ticker: 
        print_error("🏷️ Failed to find ticker symbol.")
        return jsonify(success=False, error="Could not find ticker symbol.") 
 
    stock_prices, time_labels = fetch_stock_price(ticker) 
    if not stock_prices or not time_labels: 
        print_error("📉 Failed to fetch stock prices.")
        return jsonify(success=False, error="Could not fetch stock prices.") 
 
    competitors = query_gemini_llm(summary) 
    if not competitors: 
        print_warning("🏢 No competitors found. Using default values.")
        competitors = [{"name": "No Sectors", "competitors": ["No competitors found."]}] 
 
    all_competitors = [comp for sector in competitors for comp in sector["competitors"]] 
    top_competitors = get_top_competitors(all_competitors) 
    
    print_section("🏁 Analysis complete")
    print_success(f"🎯 Successfully analyzed {company_name} ({ticker})")
    print_info(f"🏢 Found {len(all_competitors)} competitors across {len(competitors)} sectors")
    print_info(f"🥇 Top competitor: {top_competitors[0]['name'] if top_competitors else 'None'}")
 
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
    print_section("🗄️ Database initialization")
    print_info("🔧 Creating database tables if they don't exist")
    try:
        db.create_all()
        print_success("✅ Database initialized successfully")
    except Exception as e:
        print_error(f"❌ Database initialization failed: {str(e)}")

if __name__ == "__main__": 
    print_section("📈 StockMind AI")
    print_info("🚀 Starting StockMind server...")
    print_info("🌐 Open http://127.0.0.1:5000 in your browser to access the application")
    app.run(debug=True)
