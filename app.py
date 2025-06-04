from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
import secrets
from flask_session import Session
from flask_sqlalchemy import SQLAlchemy
from database_model import db
#blueprints
from auth_route import auth_bp
from backend import backend
import requests
from transformers import pipeline
import os

#app initialization
app = Flask(__name__, static_folder="static", template_folder="templates") 
CORS(app)  # Enable CORS for all routes

#configurations
app.config['SECRET_KEY'] = secrets.token_hex(32)  # Change this in production!
app.config['SESSION_TYPE'] = 'filesystem' #using server side session cookies - filesystem
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///stockmind.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

Session(app)
db.init_app(app)

app.register_blueprint(auth_bp)
app.register_blueprint(backend)

@app.route("/")
def home():
    return render_template("FRONT.html")

# News Sentiment Analysis Endpoint
@app.route('/news')
def news():
    company = request.args.get('company')
    if not company:
        return jsonify({'error': 'Missing company parameter'}), 400

    # Fetch news articles from NewsAPI
    NEWS_API_KEY = os.environ.get('NEWS_API_KEY')
    if not NEWS_API_KEY:
        return jsonify({'error': 'Missing NEWS_API_KEY in environment'}), 500
    news_url = f'https://newsapi.org/v2/everything?q={company}&sortBy=publishedAt&pageSize=10&apiKey={NEWS_API_KEY}'
    news_resp = requests.get(news_url)
    if news_resp.status_code != 200:
        return jsonify({'error': 'Failed to fetch news'}), 500
    articles = news_resp.json().get('articles', [])[:10]

    # Load sentiment analysis pipeline
    sentiment_pipeline = pipeline('sentiment-analysis', model='distilbert-base-uncased-finetuned-sst-2-english')

    results = []
    for article in articles:
        title = article.get('title', '')
        url = article.get('url', '')
        published_at = article.get('publishedAt', '')
        sentiment_result = sentiment_pipeline(title)[0]
        label = sentiment_result['label']
        score = sentiment_result['score']
        if label == 'POSITIVE':
            emoji = '😃'
        elif label == 'NEGATIVE':
            emoji = '😞'
        else:
            emoji = '😐'
        results.append({
            'title': title,
            'url': url,
            'published_at': published_at,
            'sentiment': label,
            'emoji': emoji,
            'score': score
        })
    return jsonify({'articles': results})

with app.app_context():
    db.create_all()

if __name__=="__main__":
    app.run(debug=True)