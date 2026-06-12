import os
import re
import csv
import json
import sqlite3
import smtplib
import requests
from datetime import datetime, timezone, timedelta
from collections import defaultdict, Counter
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

try:
    from textblob import TextBlob
    NLP_AVAILABLE = True
except ImportError:
    NLP_AVAILABLE = False

print("VERSION V9.0 - CRYPTO X AGENT - IMPROVED ANALYSIS")

TWITTERAPI_KEY = os.getenv("TWITTERAPI_KEY")
OUTPUT_DIR = os.getenv("OUTPUT_DIR", "reports")
MAX_TWEETS_PER_ACCOUNT = int(os.getenv("MAX_TWEETS_PER_ACCOUNT", "20"))
USE_NLP = os.getenv("USE_NLP", "true").lower() == "true"
CACHE_DB = os.getenv("CACHE_DB", "crypto_cache.db")

ACCOUNTS_LIST = [
    "BigCheds", "CryptoMichNL", "Sheldino_D", "blknoiz06", "LarpVonTrier",
    "CrashiusClay69", "cobie", "SolBigBrain", "Austin_Federa", "weremeow",
    "Virtuals_io", "DegenSpartan", "MilesDeutscher", "DefiIgnas", "TheDeFinvestor",
    "lookonchain", "nansen_ai", "DefiLlama", "zachxbt", "jessepollak",
    "0xngmi", "Route2FI", "HopiumPapi", "AltcoinSherpa", "HsakaTrades",
    "rektfencer", "Pentosh1", "TheFlowHorse", "ByzGeneral", "CryptoHayes",
    "CL207", "RunnerXBT", "MuroCrypto"
]

def init_cache_db():
    conn = sqlite3.connect(CACHE_DB)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS ticker_cache (
        ticker TEXT PRIMARY KEY,
        data TEXT,
        timestamp REAL
    )''')
    conn.commit()
    return conn

def calculate_freshness_weight(created_at_str):
    try:
        tweet_time = datetime.fromisoformat(created_at_str.replace('Z', '+00:00'))
        now = datetime.now(timezone.utc)
        hours_ago = (now - tweet_time).total_seconds() / 3600
        if hours_ago < 1:
            return 1.0
        elif hours_ago < 6:
            return 0.8
        elif hours_ago < 24:
            return 0.6
        else:
            return 0.3
    except:
        return 0.5

def analyze_sentiment_nlp(text):
    if not NLP_AVAILABLE or not USE_NLP:
        return 0.0
    try:
        blob = TextBlob(text or "")
        return float(blob.sentiment.polarity)
    except:
        return 0.0

def detect_pump_coordination(ticker_mentions):
    if len(ticker_mentions) < 3:
        return False
    authors = [m["author"] for m in ticker_mentions]
    unique_authors = len(set(authors))
    if unique_authors == 1 and len(ticker_mentions) > 2:
        return True
    return False

print("✓ V9.0 improvements loaded:")
print("  - NLP-based sentiment with TextBlob")
print("  - SQLite caching (24h TTL)")
print("  - Freshness weighting")  
print("  - Pump coordination detection")
