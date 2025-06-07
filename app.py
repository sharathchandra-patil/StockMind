from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
import secrets
from flask_session import Session
from flask_sqlalchemy import SQLAlchemy
from database_model import db
#blueprints
from auth_route import auth_bp
from backend import backend
from news_sentiment import NewsSentimentAnalyzer
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

# The /news endpoint is now handled by backend.py's /analyze_company route.
# We are removing this redundant endpoint from app.py.
# @app.route('/news')
# def news():
#     company = request.args.get('company')
#     if not company:
#         return jsonify({'error': 'Missing company parameter'}), 400

#     try:
#         news_analyzer = NewsSentimentAnalyzer()
#         articles = news_analyzer.get_news_with_sentiment(company)
#         return jsonify({'articles': articles})
#     except Exception as e:
#         return jsonify({'error': str(e)}), 500

with app.app_context():
    db.create_all()

if __name__=="__main__":
    app.run(debug=True)