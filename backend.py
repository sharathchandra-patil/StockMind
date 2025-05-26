from flask import Flask, request, jsonify, render_template, redirect, url_for, flash, session, Blueprint
from functools import wraps
import requests 
import yfinance as yf 
import wikipedia 
from google import genai 
from dotenv import load_dotenv 
import os
from alert_system.scheduler import start_scheduler, alerts
from utils import login_required
# Load environment variables from .env file
load_dotenv()

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
try:
    client = genai.Client(api_key=GEMINI_API_KEY)
except Exception as e:
    print(f"Error initializing Gemini client: {e}")
    # We'll handle this in the query_gemini_llm function

#initialize blueprint
backend = Blueprint('backend', __name__, url_prefix='/service')

@backend.route('/alert_form')
def alert_form():
    return render_template('alert_form.html')
@backend.route('/alerts')

@backend.route('/create_alert', methods=['POST'])
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

#helper functions 

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
 
def fetch_stock_price(ticker, time_range="3mo"): 
    try: 
        # Set a timeout for the request
        stock = yf.Ticker(ticker)
        # Use the provided time range
        history = stock.history(period=time_range)
        
        if history.empty:
            print(f"No stock price data found for {ticker}")
            # Generate mock data for testing
            import datetime
            import random
            today = datetime.datetime.now()
            
            # Adjust the number of days based on time range
            days = {
                "1wk": 7,
                "1mo": 30,
                "3mo": 90
            }.get(time_range, 90)
            
            time_labels = [(today - datetime.timedelta(days=i)).strftime('%Y-%m-%d') for i in range(days, 0, -1)]
            base_price = 100.0
            stock_prices = [round(base_price + random.uniform(-10, 10), 2) for _ in range(days)]
            return stock_prices, time_labels
            
        time_labels = history.index.strftime('%Y-%m-%d').tolist() 
        stock_prices = [round(price, 2) for price in history['Close'].tolist()]  # Round prices to 2 decimal places
        return stock_prices, time_labels 
    except Exception as e: 
        print(f"Error fetching stock price for {ticker}: {e}")
        # Generate mock data for testing
        import datetime
        import random
        today = datetime.datetime.now()
        
        # Adjust the number of days based on time range
        days = {
            "1wk": 7,
            "1mo": 30,
            "3mo": 90
        }.get(time_range, 90)
        
        time_labels = [(today - datetime.timedelta(days=i)).strftime('%Y-%m-%d') for i in range(days, 0, -1)]
        base_price = 100.0
        stock_prices = [round(base_price + random.uniform(-10, 10), 2) for _ in range(days)]
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
        url = "https://www.alphavantage.co/query" 
        params = { 
            "function": "SYMBOL_SEARCH", 
            "keywords": company_name, 
            "apikey": ALPHA_VANTAGE_API_KEY, 
        } 
        response = requests.get(url, params=params, timeout=3)  # 3 second timeout
        data = response.json() 
        
        # Check if we got an error message about invalid API key
        if "Error Message" in data:
            print(f"Alpha Vantage API error: {data['Error Message']}")
            # Fallback: Try to guess the ticker from the company name
            return company_name.split()[0].upper()
            
        if "bestMatches" in data: 
            for match in data["bestMatches"]: 
                if match["4. region"] == "United States": 
                    # Add to cache for future use
                    TICKER_CACHE[company_lower] = match["1. symbol"]
                    return match["1. symbol"] 
        
        # If no matches found, try to guess the ticker
        return company_name.split()[0].upper()
    except Exception as e: 
        print(f"Error in get_ticker_from_alpha_vantage: {e}")
        # Fallback: Try to guess the ticker from the company name
        return company_name.split()[0].upper()
 
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
        return stock_prices, time_labels 
    except Exception as e: 
        print(f"Error fetching stock price for competitor {ticker}: {e}")
        # Generate mock data for testing
        import datetime
        import random
        today = datetime.datetime.now()
        time_labels = [(today - datetime.timedelta(days=i)).strftime('%Y-%m-%d') for i in range(90, 0, -1)]
        base_price = 100.0
        stock_prices = [round(base_price + random.uniform(-10, 10), 2) for _ in range(90)]
        return stock_prices, time_labels
 
def get_top_competitors(competitors): 
    competitor_data = [] 
    processed_tickers = set()  # To track processed tickers and avoid duplicates 
    
    # If we don't have any competitors or encounter issues, use these fallback companies
    fallback_competitors = ["Microsoft", "Apple", "Amazon"]
    
    # Use the provided competitors or fallback if empty
    competitors_to_process = set(competitors) if competitors else fallback_competitors
 
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
    return top_competitors 
 
def query_gemini_llm(company_name): 
    try: 
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
        Based on the company name "{company_name}", provide a structured list of sectors and their main competitors.
        Focus on direct competitors in the same industry and market.
        Format: 
        Sector Name : 
            Competitor 1 
            Competitor 2 
            Competitor 3 
 
        Leave a line after each sector. Do not use bullet points. 
        Only include major, publicly traded companies that are direct competitors.
        """ 
        
        try:
            response = client.models.generate_content( 
                model="gemini-1.5-flash", contents=prompt 
            ) 
            content = response.candidates[0].content.parts[0].text
        except Exception as api_error:
            print(f"Error calling Gemini API: {api_error}")
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
        return sectors 
    except Exception as e: 
        print(f"Error in query_gemini_llm: {e}")
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
 

@backend.route("/analyze_company", methods=["GET"])
@login_required
def analyze_company():
    company_name = request.args.get("company_name")
    time_range = request.args.get("time_range", "3mo")  # Default to 3 months if not specified
    
    if not company_name:
        return jsonify(success=False, error="No company name provided.")

    _, summary = fetch_wikipedia_summary(company_name)
    if not summary:
        return jsonify(success=False, error="Could not find company description.")

    ticker = get_ticker_from_alpha_vantage(company_name)
    if not ticker:  
        return jsonify(success=False, error="Could not find ticker symbol.")

    stock_prices, time_labels = fetch_stock_price(ticker, time_range)
    if not stock_prices or not time_labels:
        return jsonify(success=False, error="Could not fetch stock prices.")

    # Only fetch competitors if this is the initial request (not a time range update)
    if time_range == "3mo":
        competitors = query_gemini_llm(company_name)  # Changed to pass company_name instead of summary
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
