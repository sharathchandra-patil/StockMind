import requests
import os
from datetime import datetime, timedelta
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
import json
from typing import List, Dict, Optional
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class NewsSentimentAnalyzer:
    """
    A class to fetch news articles and analyze their sentiment for a given company.
    """
    def __init__(self):
        # Initialize API keys from environment variables
        self.news_api_key = os.getenv('NEWS_API_KEY')
        self.alpha_vantage_key = os.getenv('ALPHA_VANTAGE_API_KEY')
        self.sentiment_analyzer = SentimentIntensityAnalyzer()
        
        # NewsAPI endpoint
        self.news_api_url = "https://newsapi.org/v2/everything"
        
        # Alpha Vantage News API endpoint (alternative)
        self.alpha_vantage_news_url = "https://www.alphavantage.co/query"
        
    def get_sentiment_emoji(self, sentiment_score: float) -> str:
        """
        Convert sentiment score to emoji representation (using VADER compound thresholds).
        
        Args:
            sentiment_score (float): VADER Compound Sentiment score (-1 to 1)
            
        Returns:
            str: Emoji representing the sentiment
        """
        if sentiment_score >= 0.05:
            return "😃"  # Positive
        elif sentiment_score <= -0.05:
            return "😞"  # Negative
        else:
            return "😐"  # Neutral
        
    def get_sentiment_label(self, sentiment_score: float) -> str:
        """
        Convert sentiment score to text label (using VADER compound thresholds).
        
        Args:
            sentiment_score (float): VADER Compound Sentiment score (-1 to 1)
            
        Returns:
            str: Text label for sentiment
        """
        if sentiment_score >= 0.05:
            return "Positive"
        elif sentiment_score <= -0.05:
            return "Negative"
        else:
            return "Neutral"
        
    def analyze_sentiment(self, text: str) -> Dict[str, float]:
        """
        Analyze sentiment of given text using VADER SentimentIntensityAnalyzer.
        
        Args:
            text (str): Text to analyze
            
        Returns:
            Dict[str, float]: Dictionary containing polarity scores (neg, neu, pos, compound)
        """
        try:
            return self.sentiment_analyzer.polarity_scores(text)
        except Exception as e:
            logger.error(f"Error analyzing sentiment with VADER: {e}")
            return {'compound': 0.0, 'neg': 0.0, 'neu': 1.0, 'pos': 0.0}
        
    def fetch_news_newsapi(self, company_name: str, days_back: int = 7) -> List[Dict]:
        """
        Fetch news articles using NewsAPI.
        
        Args:
            company_name (str): Name of the company to search for
            days_back (int): Number of days to look back for news
            
        Returns:
            List[Dict]: List of news articles with sentiment analysis
        """
        if not self.news_api_key:
            logger.error("NewsAPI key not found in environment variables")
            return []
        
        # Calculate date range
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days_back)
        
        params = {
            'q': f'"{company_name}"',
            'from': start_date.strftime('%Y-%m-%d'),
            'to': end_date.strftime('%Y-%m-%d'),
            'sortBy': 'relevancy',
            'language': 'en',
            'pageSize': 10,
            'apiKey': self.news_api_key
        }
        
        try:
            response = requests.get(self.news_api_url, params=params, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            articles = []
            
            if data.get('status') == 'ok' and data.get('articles'):
                for article in data['articles']:
                    # Analyze sentiment using VADER's compound score
                    title = article.get('title', '')
                    description = article.get('description', '')
                    content_to_analyze = f"{title}. {description}" if description else title
                    
                    sentiment_scores = self.analyze_sentiment(content_to_analyze)
                    compound_score = sentiment_scores['compound']
                    
                    article_data = {
                        'title': title,
                        'url': article.get('url', ''),
                        'published_at': article.get('publishedAt', ''),
                        'source': article.get('source', {}).get('name', 'Unknown'),
                        'description': description,
                        'sentiment_score': compound_score,
                        'sentiment_label': self.get_sentiment_label(compound_score),
                        'sentiment_emoji': self.get_sentiment_emoji(compound_score),
                        'confidence': abs(compound_score)
                    }
                    articles.append(article_data)
            
            return articles
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Error fetching news from NewsAPI: {e}")
            return []
        except Exception as e:
            logger.error(f"Unexpected error in fetch_news_newsapi: {e}")
            return []
        
    def fetch_news_alpha_vantage(self, company_ticker: str) -> List[Dict]:
        """
        Fetch news articles using Alpha Vantage News API.
        
        Args:
            company_ticker (str): Stock ticker symbol
            
        Returns:
            List[Dict]: List of news articles with sentiment analysis
        """
        if not self.alpha_vantage_key:
            logger.error("Alpha Vantage API key not found in environment variables")
            return []
        
        params = {
            'function': 'NEWS_SENTIMENT',
            'tickers': company_ticker,
            'limit': 10,
            'apikey': self.alpha_vantage_key
        }
        
        try:
            response = requests.get(self.alpha_vantage_news_url, params=params, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            articles = []
            
            if 'feed' in data:
                for article in data['feed']:
                    title = article.get('title', '')
                    # Alpha Vantage provides overall_sentiment_score, which is good. Use it if available.
                    overall_sentiment_score_str = article.get('overall_sentiment_score', '0')
                    try:
                        overall_sentiment = float(overall_sentiment_score_str)
                    except ValueError:
                        overall_sentiment = 0.0

                    # If Alpha Vantage sentiment is not meaningful (e.g., 0 or very close to 0),
                    # or if you prefer VADER for consistency, you can re-analyze.
                    # For now, let's trust Alpha Vantage's score if provided and non-zero.
                    sentiment_score_for_article = overall_sentiment
                    if abs(overall_sentiment) < 0.05: # If Alpha Vantage is neutral, use VADER for more nuanced score
                        vader_scores = self.analyze_sentiment(title)
                        sentiment_score_for_article = vader_scores['compound']
                    
                    article_data = {
                        'title': title,
                        'url': article.get('url', ''),
                        'published_at': article.get('time_published', ''),
                        'source': article.get('source', 'Unknown'),
                        'description': article.get('summary', ''),
                        'sentiment_score': sentiment_score_for_article,
                        'sentiment_label': self.get_sentiment_label(sentiment_score_for_article),
                        'sentiment_emoji': self.get_sentiment_emoji(sentiment_score_for_article),
                        'confidence': abs(sentiment_score_for_article)
                    }
                    articles.append(article_data)
            
            return articles
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Error fetching news from Alpha Vantage: {e}")
            return []
        except Exception as e:
            logger.error(f"Unexpected error in fetch_news_alpha_vantage: {e}")
            return []
        
    def get_company_news(self, company_name: str, ticker: str = None, limit: int = 10) -> List[Dict]:
        """
        Get news articles for a company using multiple sources.
        
        Args:
            company_name (str): Name of the company
            ticker (str): Stock ticker symbol (optional)
            limit (int): Maximum number of articles to return
            
        Returns:
            List[Dict]: Sorted list of news articles with sentiment analysis
        """
        all_articles = []
        
        # Try NewsAPI first
        newsapi_articles = self.fetch_news_newsapi(company_name)
        all_articles.extend(newsapi_articles)
        
        # Try Alpha Vantage if ticker is provided
        if ticker and self.alpha_vantage_key:
            av_articles = self.fetch_news_alpha_vantage(ticker)
            all_articles.extend(av_articles)
        
        # Remove duplicates based on title similarity
        unique_articles = []
        seen_titles = set()
        
        for article in all_articles:
            title_lower = article['title'].lower()
            if title_lower not in seen_titles:
                seen_titles.add(title_lower)
                unique_articles.append(article)
        
        # Sort by published date (most recent first)
        try:
            unique_articles.sort(key=lambda x: x['published_at'], reverse=True)
        except:
            logger.warning("Could not sort articles by published date.")
            pass  # If sorting fails, return unsorted
        
        return unique_articles[:limit]
        
    def format_news_output(self, articles: List[Dict]) -> str:
        """
        Format news articles for console output.
        
        Args:
            articles (List[Dict]): List of news articles
            
        Returns:
            str: Formatted string for display
        """
        if not articles:
            return "No recent news articles found for this company."
        
        output = "\n📰 Recent News & Sentiment Analysis:\n"
        output += "=" * 60 + "\n"
        
        for i, article in enumerate(articles, 1):
            output += f"\n{i}. {article['sentiment_emoji']} {article['title']}\n"
            output += f"   Source: {article['source']}\n"
            output += f"   Sentiment: {article['sentiment_label']} ({article['sentiment_score']:.2f})\n"
            output += f"   Published: {article['published_at']}\n"
            output += f"   URL: {article['url']}\n"
            
            if article.get('description'):
                output += f"   Summary: {article['description'][:100]}...\n"
            
            output += "-" * 60 + "\n"
        
        return output
        
    def get_sentiment_summary(self, articles: List[Dict]) -> Dict[str, any]:
        """
        Get overall sentiment summary from articles.
        
        Args:
            articles (List[Dict]): List of news articles
            
        Returns:
            Dict: Summary statistics
        """
        if not articles:
            return {}
        
        sentiments = [article['sentiment_score'] for article in articles]
        
        positive_count = sum(1 for s in sentiments if s >= 0.05)
        negative_count = sum(1 for s in sentiments if s <= -0.05)
        neutral_count = len(sentiments) - positive_count - negative_count
        
        average_sentiment = sum(sentiments) / len(sentiments)
        
        return {
            'total_articles': len(articles),
            'positive_count': positive_count,
            'negative_count': negative_count,
            'neutral_count': neutral_count,
            'average_sentiment': average_sentiment,
            'overall_sentiment_label': self.get_sentiment_label(average_sentiment),
            'overall_sentiment_emoji': self.get_sentiment_emoji(average_sentiment)
        } 