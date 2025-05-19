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
from dotenv import load_dotenv 
import os
import secrets
import authenticator
from alert_system.scheduler import start_scheduler, alerts
from flask_session import Session
from flask_cors import CORS
import traceback

# Load environment variables from .env file
load_dotenv()
print("API Keys loaded:")
print(f"Alpha Vantage API Key: {os.getenv('ALPHA_VANTAGE_API_KEY')}")
print(f"Gemini API Key: {os.getenv('GEMINI_API_KEY')}")
print(f"Email Address: {os.getenv('EMAIL_ADDRESS')}")

# Load API keys from environment variables
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "abc")  # Fallback to "abc" if not found
ALPHA_VANTAGE_API_KEY = os.getenv("ALPHA_VANTAGE_API_KEY", "xyz")  # Fallback to "xyz" if not found

# Cache for company tickers to avoid repeated API calls
TICKER_CACHE = {
    "apple": "AAPL",
    "microsoft": "MSFT",
    "google": "GOOGL",
    "alphabet": "GOOGL",
    "amazon": "AMZN",
    "tesla": "TSLA",
    "facebook": "META",
    "meta": "META",
    "netflix": "NFLX",
    "nvidia": "NVDA",
    "intel": "INTC",
    "amd": "AMD",
    "ibm": "IBM",
    "oracle": "ORCL",
    "salesforce": "CRM",
    "adobe": "ADBE",
    "walmart": "WMT",
    "target": "TGT",
    "coca cola": "KO",
    "pepsi": "PEP",
    "pepsico": "PEP",
    "mcdonalds": "MCD",
    "starbucks": "SBUX",
    "nike": "NKE",
    "disney": "DIS",
    "boeing": "BA",
    "ford": "F",
    "general motors": "GM",
    "exxon": "XOM",
    "chevron": "CVX",
    "jpmorgan": "JPM",
    "bank of america": "BAC",
    "goldman sachs": "GS",
    "visa": "V",
    "mastercard": "MA",
    "paypal": "PYPL",
    "johnson & johnson": "JNJ",
    "pfizer": "PFE",
    "merck": "MRK",
    "verizon": "VZ",
    "at&t": "T"
}

# Initialize Flask app
app = Flask(__name__, static_folder="static", template_folder="templates")
CORS(app)  # Enable CORS for all routes

# Configuration
app.config['SECRET_KEY'] = secrets.token_hex(32)  # Change this in production!
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///stockmind.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['JWT_SECRET_KEY'] = secrets.token_hex(32)  # For API tokens
app.config['SESSION_TYPE'] = 'filesystem' #using server side session cookies - filesystem

# Initialize Flask extensions
db = SQLAlchemy(app)
Session(app)

# Initialize Gemini client
try:
    client = genai.Client(api_key=GEMINI_API_KEY)
    print("Gemini client initialized successfully")
except Exception as e:
    print(f"Error initializing Gemini client: {e}")
    # We'll handle this in the query_gemini_llm function

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

# Helper function for authentication
def userAuthenticate():
    '''use inside route functions to block logged out user'''
    if "username" in session:
        print(f"User authenticated: {session['username']}")
        return True
    print("User not authenticated")
    return False

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
        print(f"Fetching Wikipedia summary for: {company_name}")
        
        # Clean up the company name
        # Remove common suffixes like "Inc", "Corp", etc.
        clean_name = company_name.replace(" Inc", "").replace(" Corp", "").replace(" Corporation", "")
        clean_name = clean_name.replace(" Ltd", "").replace(" LLC", "").replace(" Co", "")
        clean_name = clean_name.strip()
        
        # Create company-specific search terms
        company_terms = []
        
        # First try with company or Inc suffix to ensure we get the company, not generic terms
        company_terms.append(f"{clean_name} (company)")
        company_terms.append(f"{clean_name} Inc.")
        company_terms.append(f"{clean_name} Corporation")
        company_terms.append(f"{clean_name} company")
        
        # For common company names that might be confused with generic terms
        if clean_name.lower() in ["apple", "amazon", "target", "shell", "visa", "oracle"]:
            company_terms = [f"{clean_name} Inc.", f"{clean_name} (company)"] + company_terms
            
        # Add the original name at the end
        company_terms.append(clean_name)
        
        print(f"Trying search terms: {company_terms}")
        
        # Try each company-specific term
        for term in company_terms:
            try:
                print(f"Trying term: {term}")
                summary = wikipedia.summary(term, sentences=2)
                print(f"Found Wikipedia page for: {term}")
                return term, summary
            except wikipedia.exceptions.PageError:
                print(f"No exact match found for {term}")
                continue
            except wikipedia.exceptions.DisambiguationError as e:
                # Look for company-related options in disambiguation
                print(f"Disambiguation options for {term}: {e.options}")
                company_options = [opt for opt in e.options if any(
                    company_indicator in opt.lower() 
                    for company_indicator in ["inc", "company", "corporation", "technologies", "tech"]
                )]
                
                if company_options:
                    try:
                        company_option = company_options[0]
                        print(f"Using company-related disambiguation option: {company_option}")
                        summary = wikipedia.summary(company_option, sentences=2)
                        return company_option, summary
                    except:
                        print(f"Failed to get summary for company disambiguation option")
                        continue
                elif e.options:
                    # If no company-specific options, try the first option
                    try:
                        first_option = e.options[0]
                        summary = wikipedia.summary(first_option, sentences=2)
                        print(f"Using first disambiguation option: {first_option}")
                        return first_option, summary
                    except:
                        print(f"Failed to get summary for first disambiguation option")
                        continue
        
        # If none of the specific terms worked, perform a general search
        search_results = wikipedia.search(clean_name + " company") 
        print(f"Search results for '{clean_name} company': {search_results}")
        
        if search_results: 
            # Filter for results that look like companies
            company_results = [result for result in search_results if any(
                indicator in result.lower() 
                for indicator in ["inc", "company", "corporation", "technologies", "tech"]
            )]
            
            # Use company results if available, otherwise use regular results
            results_to_try = company_results if company_results else search_results
            
            for result in results_to_try[:2]:  # Try top 2 results
                try:
                    print(f"Trying search result: {result}")
                    summary = wikipedia.summary(result, sentences=2)
                    return result, summary
                except:
                    continue
        
        # Last resort - use stock ticker to search
        ticker = get_ticker_from_alpha_vantage(company_name)
        if ticker:
            try:
                search_with_ticker = f"{clean_name} {ticker}"
                print(f"Trying search with ticker: {search_with_ticker}")
                search_results = wikipedia.search(search_with_ticker)
                if search_results:
                    result = search_results[0]
                    summary = wikipedia.summary(result, sentences=2)
                    return result, summary
            except:
                pass
        
        # If all else fails, construct a generic description
        print(f"No Wikipedia info found, using generic description")
        generic_summary = f"{company_name} is a publicly traded company known for its products and services in the market."
        return company_name, generic_summary
            
    except Exception as e: 
        print(f"Error fetching Wikipedia summary: {str(e)}")
        # Return a generic description instead of an error
        generic_summary = f"{company_name} is a publicly traded company with operations in various industry sectors."
        return company_name, generic_summary
    
def get_company_description(company_name, ticker):
    """Get a company description from Wikipedia or generate a fallback description."""
    try:
        # First try Wikipedia
        _, summary = fetch_wikipedia_summary(company_name)
        
        # Check if the summary looks like it's about a company
        company_indicators = ["company", "corporation", "founded", "headquartered", "technology", 
                            "products", "services", "business", "industry", "market"]
        
        is_company_summary = any(indicator in summary.lower() for indicator in company_indicators)
        
        # For specific companies known to be confused with other things
        if company_name.lower() == "apple" and "fruit" in summary.lower() and "tree" in summary.lower():
            is_company_summary = False
        
        if company_name.lower() == "amazon" and "river" in summary.lower() and "rainforest" in summary.lower():
            is_company_summary = False
            
        if company_name.lower() == "shell" and "sea" in summary.lower() and not "oil" in summary.lower():
            is_company_summary = False
            
        # If the summary doesn't look like it's about a company, use a fallback
        if not is_company_summary:
            print(f"Wikipedia summary for {company_name} doesn't look like a company description")
            return generate_company_description(company_name, ticker)
            
        return summary
    except Exception as e:
        print(f"Error getting company description: {e}")
        return generate_company_description(company_name, ticker)
        
def generate_company_description(company_name, ticker):
    """Generate a generic company description using the ticker and company name."""
    # Use ticker to determine industry (basic approximation)
    tech_tickers = ["AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "INTC", "AMD", "ORCL", "IBM", "CRM"]
    finance_tickers = ["JPM", "BAC", "GS", "MS", "V", "MA", "PYPL", "AXP", "C", "WFC"]
    retail_tickers = ["WMT", "TGT", "COST", "HD", "LOW", "AMZN", "BBY", "KR"]
    energy_tickers = ["XOM", "CVX", "COP", "BP", "SHEL", "SLB", "EOG"]
    healthcare_tickers = ["JNJ", "PFE", "MRK", "ABBV", "ABT", "UNH", "CVS"]
    
    industry = "various sectors"
    if ticker in tech_tickers:
        industry = "technology"
    elif ticker in finance_tickers:
        industry = "financial services"
    elif ticker in retail_tickers:
        industry = "retail"
    elif ticker in energy_tickers:
        industry = "energy"
    elif ticker in healthcare_tickers:
        industry = "healthcare"
        
    return f"{company_name} (ticker: {ticker}) is a publicly traded company operating in the {industry} industry. It is known for its products and services in the market and competes with other major players in the sector."    

def fetch_stock_price(ticker): 
    try: 
        print(f"Fetching stock price for ticker: {ticker}")
        # Set a timeout for the request
        stock = yf.Ticker(ticker)
        # Use a longer period (3mo instead of 1mo) for more detailed response
        history = stock.history(period="3mo")
        
        if history.empty:
            print(f"No stock price data found for {ticker}")
            # Generate mock data for testing
            import datetime
            import random
            today = datetime.datetime.now()
            time_labels = [(today - datetime.timedelta(days=i)).strftime('%Y-%m-%d') for i in range(90, 0, -1)]
            base_price = 100.0
            stock_prices = [round(base_price + random.uniform(-10, 10), 2) for _ in range(90)]
            return stock_prices, time_labels
            
        time_labels = history.index.strftime('%Y-%m-%d').tolist() 
        stock_prices = [round(price, 2) for price in history['Close'].tolist()]  # Round prices to 2 decimal places
        print(f"Stock price data retrieved successfully. Latest price: ${stock_prices[-1]}")
        return stock_prices, time_labels 
    except Exception as e: 
        print(f"Error fetching stock price for {ticker}: {e}")
        traceback.print_exc()
        # Generate mock data for testing
        import datetime
        import random
        today = datetime.datetime.now()
        time_labels = [(today - datetime.timedelta(days=i)).strftime('%Y-%m-%d') for i in range(90, 0, -1)]
        base_price = 100.0
        stock_prices = [round(base_price + random.uniform(-10, 10), 2) for _ in range(90)]
        return stock_prices, time_labels

def get_ticker_from_alpha_vantage(company_name): 
    # Check if company is in our cache first
    company_lower = company_name.lower()
    for key, ticker in TICKER_CACHE.items():
        if key in company_lower:
            print(f"Using cached ticker {ticker} for {company_name}")
            return ticker
    
    # If not in cache, try API with a short timeout
    try: 
        print(f"Fetching ticker for {company_name} from Alpha Vantage")
        url = "https://www.alphavantage.co/query" 
        params = { 
            "function": "SYMBOL_SEARCH", 
            "keywords": company_name, 
            "apikey": ALPHA_VANTAGE_API_KEY, 
        }
        
        print(f"API request params: {params}")
        response = requests.get(url, params=params, timeout=3)  # 3 second timeout
        print(f"API response status code: {response.status_code}")
        
        data = response.json()
        print(f"API response data: {data}")
        
        # Check if we got an error message about invalid API key
        if "Error Message" in data:
            print(f"Alpha Vantage API error: {data['Error Message']}")
            # Fallback: Try to guess the ticker from the company name
            fallback_ticker = company_name.split()[0].upper()
            print(f"Using fallback ticker: {fallback_ticker}")
            return fallback_ticker
            
        if "bestMatches" in data: 
            for match in data["bestMatches"]: 
                if match["4. region"] == "United States": 
                    # Add to cache for future use
                    ticker = match["1. symbol"]
                    TICKER_CACHE[company_lower] = ticker
                    print(f"Found ticker from API: {ticker}")
                    return ticker
            
        # If no matches found, try to guess the ticker
        fallback_ticker = company_name.split()[0].upper()
        print(f"No matches found, using fallback ticker: {fallback_ticker}")
        return fallback_ticker
    except Exception as e: 
        print(f"DETAILED Error in get_ticker_from_alpha_vantage: {str(e)}")
        traceback.print_exc()
        # Fallback: Try to guess the ticker from the company name
        fallback_ticker = company_name.split()[0].upper()
        print(f"Error occurred, using fallback ticker: {fallback_ticker}")
        return fallback_ticker
 
def fetch_market_cap(ticker): 
    try: 
        print(f"Fetching market cap for: {ticker}")
        stock = yf.Ticker(ticker) 
        market_cap = stock.info.get('marketCap', None)
        if market_cap:
            print(f"Market cap for {ticker}: {market_cap}")
        else:
            print(f"No market cap found for {ticker}")
        return market_cap 
    except Exception as e:
        print(f"Error fetching market cap: {e}")
        traceback.print_exc()
        return None 
 
def get_stock_price_for_competitor(ticker): 
    try: 
        print(f"Fetching stock price for competitor: {ticker}")
        stock = yf.Ticker(ticker) 
        # Use a longer period (3mo instead of 1mo) for more detailed response
        history = stock.history(period="3mo") 
        
        if history.empty:
            print(f"No stock price data found for competitor {ticker}")
            # Generate mock data for testing
            import datetime
            import random
            today = datetime.datetime.now()
            time_labels = [(today - datetime.timedelta(days=i)).strftime('%Y-%m-%d') for i in range(90, 0, -1)]
            base_price = 100.0
            stock_prices = [round(base_price + random.uniform(-10, 10), 2) for _ in range(90)]
            return stock_prices, time_labels
            
        time_labels = history.index.strftime('%Y-%m-%d').tolist() 
        stock_prices = [round(price, 2) for price in history['Close'].tolist()]  # Round prices to 2 decimal places
        print(f"Stock data for competitor {ticker} retrieved successfully")
        return stock_prices, time_labels 
    except Exception as e: 
        print(f"Error fetching stock price for competitor {ticker}: {e}")
        traceback.print_exc()
        # Generate mock data for testing
        import datetime
        import random
        today = datetime.datetime.now()
        time_labels = [(today - datetime.timedelta(days=i)).strftime('%Y-%m-%d') for i in range(90, 0, -1)]
        base_price = 100.0
        stock_prices = [round(base_price + random.uniform(-10, 10), 2) for _ in range(90)]
        return stock_prices, time_labels
 
def get_top_competitors(competitors): 
    print(f"Getting top competitors for: {competitors}")
    competitor_data = [] 
    processed_tickers = set()  # To track processed tickers and avoid duplicates 
    
    # If we don't have any competitors or encounter issues, use these fallback companies
    fallback_competitors = ["Microsoft", "Apple", "Amazon"]
    
    # Use the provided competitors or fallback if empty
    competitors_to_process = set(competitors) if competitors else fallback_competitors
    print(f"Processing competitors: {competitors_to_process}")
 
    for competitor in competitors_to_process:  # Remove duplicate names 
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
    
    # If we couldn't get any valid competitor data, use fallback data
    if not competitor_data:
        print("No valid competitor data found, using fallback data")
        # Create some fallback data with mock values
        import random
        for i, comp in enumerate(fallback_competitors):
            ticker = comp[0:3].upper()  # Just use first 3 letters as ticker
            mock_market_cap = 1000000000 * (3-i)  # Decreasing market caps
            # Add random walk for mock prices to avoid straight lines
            mock_prices = []
            price = 100 + i*10
            for j in range(30):
                price += random.uniform(-2, 2)
                mock_prices.append(round(price, 2))
            mock_dates = [f"2025-04-{j+1:02d}" for j in range(30)]  # Mock dates
            
            competitor_data.append({
                "name": comp,
                "ticker": ticker,
                "market_cap": mock_market_cap,
                "stock_prices": mock_prices,
                "time_labels": mock_dates,
                "stock_price": mock_prices[-1],
            })
 
    # Sort competitors by market cap and return the top 3 
    top_competitors = sorted(competitor_data, key=lambda x: x["market_cap"], reverse=True)[:3]
    print(f"Top competitors identified: {[comp['name'] for comp in top_competitors]}")
    return top_competitors 
 
def query_gemini_llm(description): 
    try: 
        print(f"Querying Gemini LLM with description: {description[:100]}...")
        # Check if client is defined (it might not be if API key is invalid)
        if 'client' not in globals():
            print("Gemini client not initialized, using fallback data")
            # Return fallback data
            return [
                {
                    "name": "Technology Sector:",
                    "competitors": ["Microsoft", "Apple", "IBM", "Oracle"]
                },
                {
                    "name": "Financial Sector:",
                    "competitors": ["JPMorgan Chase", "Bank of America", "Wells Fargo", "Citigroup"]
                }
            ]
            
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
        
        try:
            print("Sending request to Gemini API...")
            response = client.models.generate_content( 
                model="gemini-1.5-flash", contents=prompt 
            ) 
            content = response.candidates[0].content.parts[0].text
            print(f"Received response from Gemini: {content[:100]}...")
        except Exception as api_error:
            print(f"Error calling Gemini API: {api_error}")
            traceback.print_exc()
            # Return fallback data
            return [
                {
                    "name": "Technology Sector:",
                    "competitors": ["Microsoft", "Apple", "IBM", "Oracle"]
                },
                {
                    "name": "Financial Sector:",
                    "competitors": ["JPMorgan Chase", "Bank of America", "Wells Fargo", "Citigroup"]
                }
            ]
            
        sectors = [] 
        for line in content.split("\n\n"): 
            lines = line.strip().split("\n") 
            if len(lines) > 1: 
                sector_name = lines[0].strip() 
                competitors = [l.strip() for l in lines[1:]] 
                sectors.append({"name": sector_name, "competitors": competitors}) 
        
        print(f"Processed {len(sectors)} sectors from Gemini response")
        return sectors 
    except Exception as e: 
        print(f"Error in query_gemini_llm: {e}")
        traceback.print_exc()
        # Return fallback data
        return [
            {
                "name": "Technology Sector:",
                "competitors": ["Microsoft", "Apple", "IBM", "Oracle"]
            },
            {
                "name": "Financial Sector:",
                "competitors": ["JPMorgan Chase", "Bank of America", "Wells Fargo", "Citigroup"]
            }
        ]

# Start the scheduler for alerts
start_scheduler()

# Test routes for debugging
@app.route("/test_auth")
def test_auth():
    if userAuthenticate():
        return jsonify({"authenticated": True, "username": session.get("username")})
    else:
        return jsonify({"authenticated": False})

@app.route("/test_alpha_vantage")
def test_alpha_vantage():
    try:
        result = get_ticker_from_alpha_vantage("Apple")
        return jsonify({"success": True, "ticker": result})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@app.route("/test_gemini")
def test_gemini():
    try:
        result = query_gemini_llm("Apple is a technology company that designs, manufactures, and markets smartphones, personal computers, tablets, wearables, and accessories.")
        return jsonify({"success": True, "data": result})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

# Routes for alert system
@app.route('/alert_form')
def alert_form():
    return render_template('alert_form.html')

@app.route('/alerts')
def view_alerts():
    return render_template('alert_form.html', alerts=alerts)

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

# Main route
@app.route("/") 
def home(): 
    return render_template("FRONT.html") 

# Authentication routes
@app.route('/access-account')
def accessAccount():
    return render_template("access-account.html")

@app.route("/login", methods=['POST'])
def login():
    email = request.form['email']
    password = request.form['password']
    if(not email or not password):
        return render_template("access-account.html", error="Invalid Information, Please try again")
    user = User.query.filter_by(email=email).first()
    if(user and user.check_password(password)):
        username = user.username
        session["username"] = username
        print(f"User logged in: {username}")
        return redirect(url_for("home"))
    else:
        return render_template("access-account.html", error="Invalid Information")
        
@app.route("/register", methods=['POST'])
def register():
    username = request.form['username']
    email = request.form['email']
    password = request.form['password']
    if(not username or not email or not password):
        return render_template("access-account.html", error="Invalid Information, Please try again")
    user = User.query.filter_by(email=email).first()
    if user:
        return render_template("access-account.html", error="Account Already Exist")
    else:
        new_user = User(username=username, email=email)
        new_user.set_passsword(password)
        session['username'] = username
        session['password'] = new_user.get_passw_hash()
        session['email'] = email
        print(f"New user registration initiated: {username} / {email}")
        return redirect(url_for('auth'))
    
@app.route('/api/auth')
def auth():
    username = session['username']
    email = session['email']
    try:
        print(f"Generating OTP for: {username} / {email}")
        otp = authenticator.generateOTP(username=username, usermail=email)
        session["otp"] = otp
        print(f"OTP generated successfully: {otp}")
    except Exception as e:
        print(f"Error generating OTP: {e}")
        traceback.print_exc()
        return render_template("access-account.html", error="Invalid email address or email configuration")
    return render_template("access-account.html", otp=True)

@app.route('/api/verify', methods=['POST'])
def verify():
    inp = request.form['userOTP']
    username = session["username"]
    password = session["password"]
    email = session["email"]
    otp = session["otp"]
    print(f"Verifying OTP for: {username} / {email}")
    print(f"Input OTP: {inp}, Stored OTP: {otp}")
    
    session.pop("password", None)
    session.pop("email", None)
    session.pop("otp", None)
    authSuccess = authenticator.verifyOTP(otp, inp)
    if(authSuccess):
        print(f"OTP verification successful for {username}")
        newUser = User(username=username, email=email, password_hash=password)
        #registering the user in database
        db.session.add(newUser)
        db.session.commit()
        print(f"User registered in database: {username}")
        return redirect(url_for('home'))
    else:
        print(f"OTP verification failed for {username}")
        session.pop("username", None)
        return render_template("FRONT.html", error="❌ Invalid OTP")
    
@app.route('/logout')
def logout():
    print(f"User logged out: {session.get('username')}")
    session.pop("username", None)
    return redirect(url_for('home'))

# API route for analyzing companies
@app.route("/analyze_company", methods=["GET"]) 
def analyze_company(): 
    print(f"Session data: {session}")
    print(f"User authenticated: {userAuthenticate()}")
    
    # TEMPORARY: For testing, comment out authentication check
    # if not userAuthenticate():
    #    return jsonify(success=False, error="Please sign in to continue")
    
    try:
        company_name = request.args.get("company_name") 
        print(f"Analyzing company: {company_name}")
        
        if not company_name: 
            return jsonify(success=False, error="No company name provided.") 
     
        # First get the ticker - we'll need this for better company descriptions
        ticker = get_ticker_from_alpha_vantage(company_name) 
        if not ticker: 
            ticker = company_name.split()[0].upper()
            print(f"Using fallback ticker {ticker} for {company_name}")
        
        # Get a company-specific description
        summary = get_company_description(company_name, ticker)
        print(f"Company description: {summary[:100]}...")
     
        stock_prices, time_labels = fetch_stock_price(ticker) 
        if not stock_prices or not time_labels: 
            print(f"Using mock stock data for {ticker}")
            stock_prices = [100 + i for i in range(30)]
            time_labels = [f"2025-04-{i+1:02d}" for i in range(30)]
     
        competitors = query_gemini_llm(summary) 
        if not competitors: 
            competitors = [{"name": "No Sectors", "competitors": ["No competitors found."]}] 
     
        # Use only the first sector's competitors for top competitors
        if competitors and competitors[0].get("competitors"):
            relevant_competitors = competitors[0]["competitors"]
        else:
            relevant_competitors = []
        print(f"Relevant competitors for {company_name}: {relevant_competitors}")
        top_competitors = get_top_competitors(relevant_competitors)
        print(f"Top competitors data for {company_name}:")
        for comp in top_competitors:
            print(f"  {comp['name']} | Ticker: {comp['ticker']} | Market Cap: {comp['market_cap']} | Last Price: {comp['stock_price']}")
     
        print("Successfully analyzed company, returning data")
        return jsonify( 
            success=True, 
            description=summary, 
            ticker=ticker, 
            stock_prices=stock_prices, 
            time_labels=time_labels, 
            competitors=competitors, 
            top_competitors=top_competitors, 
        )
    except Exception as e:
        print(f"Error in analyze_company: {e}")
        traceback.print_exc()
        return jsonify(
            success=False, 
            error=f"An error occurred while analyzing the company: {str(e)}"
        )

# Initialize database
with app.app_context():
    db.create_all()

if __name__ == "__main__": 
    # Get port and host from environment variables
    port = int(os.getenv("PORT", 12001))
    host = os.getenv("HOST", "0.0.0.0")
    print(f"Starting server on {host}:{port}")
    app.run(host=host, port=port, debug=True)
