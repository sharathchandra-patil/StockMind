from flask import Flask, request, jsonify, render_template, redirect, url_for, flash, session
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
import authenticator
from alert_system.scheduler import start_scheduler, alerts
from flask_session import Session

#INITIAILIZE APP
app = Flask(__name__, static_folder="static", template_folder="templates")

# Configuration
app.config['SECRET_KEY'] = secrets.token_hex(32)  # Change this in production!
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///stockmind.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['JWT_SECRET_KEY'] = secrets.token_hex(32)  # For API tokens
app.config['SESSION_TYPE'] = 'filesystem' #using server side session cookies - filesystem

# Initialize Flask extensions
db = SQLAlchemy(app)
Session(app)

# Load API keys 
GEMINI_API_KEY = "your_gemini_apikey"  # GeminiAPIKey 
#!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
ALPHA_VANTAGE_API_KEY = "your_alpha_vantage_key"  # AlphaVantageAPIKey 
client = genai.Client(api_key=GEMINI_API_KEY)


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

# User model
class User(db.Model):
    id = db.Column(db.Integer, primary_key = True)
    username = db.Column(db.String(50), nullable = False)
    email = db.Column(db.String(120), unique=True, nullable = False)
    password_hash = db.Column(db.String(200), nullable = False)
    def set_passsword(self, passw):
        self.password_hash = generate_password_hash(passw)
    def check_password(self, passw):
        return check_password_hash(self.password_hash, passw)
    def get_passw_hash(self):
        return self.password_hash

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
    try: 
        search_results = wikipedia.search(company_name) 
        if search_results: 
            page_title = search_results[0] 
            summary = wikipedia.summary(page_title, sentences=2) 
            return page_title, summary 
    except Exception as e: 
        return None, f"Error fetching Wikipedia summary: {str(e)}" 
    return None, "No Wikipedia page found for the given company." 
 
def fetch_stock_price(ticker): 
    try: 
        stock = yf.Ticker(ticker) 
        history = stock.history(period="3mo") 
        time_labels = history.index.strftime('%Y-%m-%d').tolist() 
        stock_prices = [round(price, 2) for price in history['Close'].tolist()]  # Round prices to 2 decimal places
        return stock_prices, time_labels 
    except Exception as e: 
        return None, None
 
def get_ticker_from_alpha_vantage(company_name): 
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
                    return match["1. symbol"] 
        return None 
    except Exception as e: 
        return None 
 
def fetch_market_cap(ticker): 
    try: 
        stock = yf.Ticker(ticker) 
        market_cap = stock.info.get('marketCap', None) 
        return market_cap 
    except Exception as e: 
        return None 
 
def get_stock_price_for_competitor(ticker): 
    try: 
        stock = yf.Ticker(ticker) 
        history = stock.history(period="3mo") 
        time_labels = history.index.strftime('%Y-%m-%d').tolist() 
        stock_prices = history['Close'].tolist() 
        return stock_prices, time_labels 
    except Exception as e: 
        return None, None 
 
def get_top_competitors(competitors): 
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
    return top_competitors 
 
def query_gemini_llm(description): 
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
        return sectors 
    except Exception as e: 
        return None 
 
def userAuthenticate():
    '''use inside route functions to block logged out user'''
    if "username" in session:
        return True
    return False

# Authentication Routes
@app.route("/login", methods = ['POST'])
def login():
    email = request.form['email']
    password = request.form['password']
    if(not email or not password):
        return render_template("access-account.html", error = "Invalid Information, Please try again")
    user = User.query.filter_by(email = email).first()
    if(user and user.check_password(password)):
        username = user.username
        session["username"] = username
        return redirect(url_for("home"))
    else:
        return render_template("access-account.html", error = "Invalid Information")
        

@app.route("/register", methods = ['POST'])
def register():
    username = request.form['username']
    email = request.form['email']
    password = request.form['password']
    if(not username or not email or not password):
        return render_template("access-account.html", error = "Invalid Information, Please try again")
    user = User.query.filter_by(email = email).first()
    if user:
        return render_template("access-account.html", error="Account Already Exist")
    else:
        new_user = User(username = username, email = email)
        new_user.set_passsword(password)
        session['username'] = username
        session['password'] = new_user.get_passw_hash()
        session['email'] = email
        return redirect(url_for('auth'))
    
@app.route('/api/auth')
def auth():
    username = session['username']
    email = session['email']
    try:
        otp =  authenticator.generateOTP(username=username, usermail=email)
        session["otp"] = otp
    except:
        return render_template("access-account.html", error = "Invalid email address")
    return render_template("access-account.html", otp = True)

@app.route('/api/verify', methods = ['POST'])
def verify():
    inp = request.form['userOTP']
    username = session["username"]
    password= session["password"]
    email = session["email"]
    otp = session["otp"]
    session.pop("password",None)
    session.pop("email",None)
    session.pop("otp",None)
    authSuccess = authenticator.verifyOTP(otp, inp)
    if(authSuccess):
        newUser = User(username = username , email = email, password_hash = password)
        #registering the user in database
        db.session.add(newUser)
        db.session.commit()
        return redirect(url_for('home'))
    else:
        session.pop("username",None)
        return render_template("FRONT.html", error = "❌ Invalid OTP")
    
@app.route('/logout')
def logout():
    session.pop("username", None)
    return redirect(url_for('home'))
@app.route('/access-account')
def accessAccount():
    return render_template("access-account.html")

# Protect existing routes
@app.route("/")
def home():
    return render_template("FRONT.html")

@app.route("/analyze_company", methods=["GET"])
def analyze_company():
    if not userAuthenticate():
        return render_template("FRONT.html", error = "Please Sign In to continue")
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
