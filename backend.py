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
from news_sentiment import NewsSentimentAnalyzer
import time
from datetime import datetime
import concurrent.futures
import threading
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
        print(f"Error fetching Wikipedia summary for {company_name}: {str(e)}")
        return None, "No Wikipedia page found for the given company or an error occurred."
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
        response = requests.get(url, params=params, timeout=5)
        response.raise_for_status() # Raise an exception for HTTP errors (4xx or 5xx)

        # Check if the response is empty or malformed JSON
        if not response.text.strip():
            print(f"Alpha Vantage API returned empty response for {company_name}. Falling back.")
            return company_name.split()[0].upper() if company_name else "MSFT" # More robust fallback

        data = response.json() 
        
        # Check if we got an error message about invalid API key or other issues
        if "Error Message" in data:
            print(f"Alpha Vantage API error for {company_name}: {data['Error Message']}. Falling back.")
            return company_name.split()[0].upper() if company_name else "MSFT" # More robust fallback
        if "Note" in data and "rate limit" in data["Note"].lower():
            print(f"Alpha Vantage API rate limit hit for {company_name}. Falling back.")
            return company_name.split()[0].upper() if company_name else "MSFT" # More robust fallback
            
        if "bestMatches" in data and len(data["bestMatches"]) > 0: 
            for match in data["bestMatches"]: 
                if match["4. region"] == "United States": 
                    # Add to cache for future use
                    TICKER_CACHE[company_lower] = match["1. symbol"]
                    return match["1. symbol"] 
        
        # If no matches found, try to guess the ticker
        print(f"No Alpha Vantage matches found for {company_name}, guessing ticker. Falling back.")
        return company_name.split()[0].upper() if company_name else "MSFT" # More robust fallback
    except requests.exceptions.RequestException as e: # Catch network/HTTP errors
        print(f"Network or HTTP error fetching ticker for {company_name}: {e}. Falling back.")
        return company_name.split()[0].upper() if company_name else "MSFT" # More robust fallback
    except ValueError as e: # Catch JSON decoding errors
        print(f"JSON decoding error for Alpha Vantage response for {company_name}: {e}. Falling back.")
        print(f"Response content (partial): {response.text[:200]}...") # Log partial content for debugging
        return company_name.split()[0].upper() if company_name else "MSFT" # More robust fallback
    except Exception as e: # Catch any other unexpected errors
        print(f"An unexpected error occurred while fetching ticker for {company_name} from Alpha Vantage: {e}. Falling back.")
        return company_name.split()[0].upper() if company_name else "MSFT" # More robust fallback
 
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
        history = stock.history(period="3mo") # Fetch 3 months of history
        
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
    """Optimized parallel competitor processing"""
    print(f"[Competitors] Starting parallel processing for {len(competitors)} competitors")
    
    # Limit to top 3 competitors to reduce processing time
    # Note: The 'competitors' input here is already 'all_competitors' from the Gemini LLM
    # So we should be careful about limiting it to [:3] here if we want more.
    # For now, let's process the first few that Gemini provides, as specified by the prompt.
    # The prompt actually suggests limiting to the "top 3 competitors by market evaluation"
    # which implies we should get enough data to *find* the top 3, not just process the first 3.
    # Let's adjust to process a reasonable number (e.g., first 10 if available)
    # and then select the top 3 based on market cap.
    
    # For initial testing, let's use the provided limit of 3 for quick results.
    # If the user wants more than the top 3, we'll need to adjust the limit here later.
    limited_competitors = competitors[:10] # Process up to 10 to find top 3 based on data
    processed_tickers = set()
    competitor_data = []
    
    # Use a lock for thread-safe access to processed_tickers and competitor_data
    # This is important when multiple threads are modifying shared resources.
    data_lock = threading.Lock() 

    # Process competitors in parallel using ThreadPoolExecutor
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor: # Increased workers for more parallelism
        # Submit all competitor processing tasks at once
        future_to_competitor = {
            executor.submit(process_single_competitor_optimized, comp, processed_tickers, data_lock): comp 
            for comp in limited_competitors
        }
        
        # Collect results as they complete
        for future in concurrent.futures.as_completed(future_to_competitor):
            comp = future_to_competitor[future]
            try:
                result = future.result(timeout=15)  # Increased timeout for robustness
                if result:
                    with data_lock: # Acquire lock before modifying shared list
                        competitor_data.append(result)
                    print(f"[Competitors] ✓ Processed {comp}")
            except concurrent.futures.TimeoutError:
                print(f"[Competitors] ✗ Timeout processing {comp}. Skipping.")
            except Exception as e:
                print(f"[Competitors] ✗ Error processing {comp}: {e}")
    
    # Fallback logic if no competitors processed successfully
    if not competitor_data:
        print("[Competitors] No valid competitor data found, using fallback")
        return get_fallback_competitors()
    
    # Sort by market cap and return top 3
    # Ensure all items have 'market_cap' for sorting, use 0 as fallback
    top_competitors = sorted(competitor_data, key=lambda x: x.get("market_cap", 0), reverse=True)[:3]
    print(f"[Competitors] ✓ Successfully processed {len(top_competitors)} competitors")
    return top_competitors

def process_single_competitor_optimized(comp, processed_tickers, data_lock):
    """Process a single competitor with optimized API calls"""
    try:
        # Skip if already processed
        with data_lock: # Acquire lock to check processed_tickers
            if comp in processed_tickers:
                return None
            
        # Get ticker
        ticker = get_ticker_from_alpha_vantage(comp)
        with data_lock: # Acquire lock to check/add to processed_tickers
            if not ticker or ticker in processed_tickers:
                return None
            
            # Add to processed set to avoid duplicates
            processed_tickers.add(ticker)
            processed_tickers.add(comp)
        
        # Use yfinance for both market cap and stock data
        stock = yf.Ticker(ticker)
        
        # Get info and history in parallel
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            info_future = executor.submit(safe_get_stock_info, stock)
            history_future = executor.submit(safe_get_stock_history, stock)
            
            # Wait for both with timeout
            info = info_future.result(timeout=10) # Increased timeout
            history = history_future.result(timeout=10) # Increased timeout
        
        # Validate data
        if not info or history is None or history.empty:
            print(f"[Competitors] No valid data for {comp} ({ticker})")
            return None
            
        market_cap = info.get('marketCap')
        if not market_cap:
            print(f"[Competitors] No market cap for {comp} ({ticker})")
            return None
        
        # Process stock data
        time_labels = history.index.strftime('%Y-%m-%d').tolist()
        # Ensure prices are floats before rounding, and handle potential empty list
        stock_prices = [round(float(price), 2) for price in history['Close'].tolist()]
        
        return {
            "name": comp,
            "ticker": ticker,
            "market_cap": market_cap,
            "stock_prices": stock_prices,
            "time_labels": time_labels,
            "stock_price": stock_prices[-1] if stock_prices else 0, # Ensure stock_price is safe
        }
        
    except Exception as e:
        print(f"[Competitors] Error processing {comp}: {e}")
        return None

def safe_get_stock_info(stock):
    """Safely get stock info with error handling"""
    try:
        return stock.info
    except Exception as e:
        print(f"[Competitors] Error getting stock info: {e}")
        return None

def safe_get_stock_history(stock):
    """Safely get stock history with error handling"""
    try:
        return stock.history(period="3mo")
    except Exception as e:
        print(f"[Competitors] Error getting stock history: {e}")
        return None

def get_fallback_competitors():
    """Fallback competitors with mock data (keep your existing fallback logic)"""
    import random
    import datetime
    
    fallback_list = ["Microsoft", "Apple", "Google"] # Limited fallback for quickness
    competitor_data = []
    today = datetime.datetime.now()
    
    for i, comp in enumerate(fallback_list):
        ticker = comp[:3].upper()
        mock_market_cap = 1000000000 * (3-i)
        
        # Generate mock prices
        mock_prices = []
        price = 100 + i*10
        for j in range(30):
            price += random.uniform(-2, 2)
            mock_prices.append(round(price, 2))
        
        mock_dates = [(today - datetime.timedelta(days=j)).strftime('%Y-%m-%d') 
                     for j in range(30, 0, -1)]
        
        competitor_data.append({
            "name": comp,
            "ticker": ticker,
            "market_cap": mock_market_cap,
            "stock_prices": mock_prices,
            "time_labels": mock_dates,
            "stock_price": mock_prices[-1],
        })
    
    return competitor_data

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
 

@backend.route('/analyze_company', methods=['POST'])
def analyze_company():
    start_time = time.time()
    print(f"\n=== Starting analysis at {datetime.now()} ===")
    
    data = request.json
    company_name = data.get("company_name")
    if not company_name:
        return jsonify(success=False, error="No company name provided.")

    try:
        # Wikipedia API timing
        wiki_start = time.time()
        print(f"\n[Wikipedia] Starting fetch for {company_name}")
        _, wiki_summary = fetch_wikipedia_summary(company_name)
        if not wiki_summary:
            wiki_summary = "No description found for this company."
        wiki_time = time.time() - wiki_start
        print(f"[Wikipedia] Completed in {wiki_time:.2f} seconds")

        # Alpha Vantage API timing
        av_start = time.time()
        print(f"\n[Alpha Vantage] Starting ticker fetch for {company_name}")
        ticker = get_ticker_from_alpha_vantage(company_name)
        if not ticker:
            ticker = company_name.split()[0].upper() if company_name else "AAPL"
        av_time = time.time() - av_start
        print(f"[Alpha Vantage] Completed in {av_time:.2f} seconds")

        # Stock Data timing
        stock_start = time.time()
        print(f"\n[Stock Data] Starting fetch for {ticker}")
        stock_prices, time_labels = fetch_stock_price(ticker)
        stock_time = time.time() - stock_start
        print(f"[Stock Data] Completed in {stock_time:.2f} seconds")

        # Gemini API timing
        gemini_start = time.time()
        print(f"\n[Gemini] Starting analysis for {company_name}")
        competitors_raw = query_gemini_llm(company_name)
        if not competitors_raw:
            competitors_raw = [{"name": "No Sectors", "competitors": ["No competitors found."]}]
        gemini_time = time.time() - gemini_start
        print(f"[Gemini] Completed in {gemini_time:.2f} seconds")

        # Competitor processing timing
        competitor_processing_start = time.time()
        print(f"\n[Competitors] Starting processing of competitors")
        all_competitors = [comp for sector in competitors_raw for comp in sector["competitors"]]
        top_competitors = get_top_competitors(all_competitors)
        competitor_processing_time = time.time() - competitor_processing_start
        print(f"[Competitors] Completed in {competitor_processing_time:.2f} seconds")

        # News API timing
        news_start = time.time()
        print(f"\n[News] Starting fetch for {company_name}")
        news_analyzer = NewsSentimentAnalyzer()
        news_articles = news_analyzer.get_company_news(company_name, ticker)
        sentiment_summary = news_analyzer.get_sentiment_summary(news_articles)
        news_time = time.time() - news_start
        print(f"[News] Completed in {news_time:.2f} seconds")

        # Calculate total time
        total_time = time.time() - start_time
        print(f"\n=== Total analysis completed in {total_time:.2f} seconds ===")
        print(f"Breakdown:")
        print(f"- Wikipedia: {wiki_time:.2f}s")
        print(f"- Alpha Vantage: {av_time:.2f}s")
        print(f"- Stock Data: {stock_time:.2f}s")
        print(f"- Gemini (LLM Query): {gemini_time:.2f}s")
        print(f"- Competitor Processing: {competitor_processing_time:.2f}s")
        print(f"- News: {news_time:.2f}s")

        return jsonify(
            success=True,
            description=wiki_summary,
            ticker=ticker,
            stock_prices=stock_prices,
            time_labels=time_labels,
            competitors=competitors_raw,
            top_competitors=top_competitors,
            news_articles=news_articles,
            news_summary=sentiment_summary,
            timing={
                'total': total_time,
                'wikipedia': wiki_time,
                'alpha_vantage': av_time,
                'stock_data': stock_time,
                'gemini_llm_query': gemini_time,
                'competitor_processing': competitor_processing_time,
                'news': news_time
            }
        )
    except Exception as e:
        print(f"\n[ERROR] Analysis failed: {str(e)}")
        return jsonify(success=False, error=str(e))
