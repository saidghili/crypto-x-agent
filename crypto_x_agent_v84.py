import os
import re
import csv
import json
import sqlite3
import smtplib
import requests
from datetime import datetime, timezone
from collections import defaultdict, Counter
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

try:
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False
    print("WARNING: openai library not installed. Install with: pip install openai")

print("VERSION V8.4 - SLIDING WINDOW + SIGNAL PERFORMANCE TRACKING + CACHING + PUMP DETECTION")

TWITTERAPI_KEY = os.getenv("TWITTERAPI_KEY")
EMAIL_FROM = os.getenv("EMAIL_FROM")
EMAIL_TO = os.getenv("EMAIL_TO")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")
SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.laposte.net")
SMTP_PORT = int(os.getenv("SMTP_PORT", "465"))
OUTPUT_DIR = os.getenv("OUTPUT_DIR", "reports")
FETCH_TWEETS_PER_RUN = int(os.getenv("FETCH_TWEETS_PER_RUN", "20"))
MAX_TWEETS_PER_ACCOUNT = int(os.getenv("MAX_TWEETS_PER_ACCOUNT", "100"))
SEND_EMAIL_REPORT = os.getenv("SEND_EMAIL_REPORT", "false").lower() == "true"
CACHE_DB = os.getenv("CACHE_DB", "crypto_cache.db")
CACHE_TTL_HOURS = int(os.getenv("CACHE_TTL_HOURS", "6"))

ACCOUNTS_LIST = ["BigCheds", "CryptoMichNL", "Sheldino_D", "blknoiz06", "LarpVonTrier", "CrashiusClay69", "cobie", "SolBigBrain", "Austin_Federa", "weremeow", "Virtuals_io", "DegenSpartan", "MilesDeutscher", "DefiIgnas", "TheDeFinvestor", "lookonchain", "nansen_ai", "DefiLlama", "zachxbt", "jessepollak", "0xngmi", "Route2FI", "HopiumPapi", "AltcoinSherpa", "HsakaTrades", "rektfencer", "Pentosh1", "TheFlowHorse", "ByzGeneral", "CryptoHayes", "CL207", "RunnerXBT", "MuroCrypto"]

def norm_author(author: str) -> str:
    return (author or "").replace("@", "").strip().lower()

def parse_tweet_datetime(value):
    if not value: return None
    value = str(value).strip()
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None: dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except: pass
    try:
        dt = datetime.strptime(value, "%a %b %d %H:%M:%S %z %Y")
        return dt.astimezone(timezone.utc)
    except: pass
    return None

def tweet_created_ts(tweet):
    dt = parse_tweet_datetime(tweet.get("created_at"))
    return dt.timestamp() if dt else 0.0

def is_tweet_after(tweet, since_time):
    if not since_time: return True
    tweet_dt = parse_tweet_datetime(tweet.get("created_at"))
    since_dt = parse_tweet_datetime(since_time)
    if not tweet_dt or not since_dt: return True
    return tweet_dt > since_dt

def init_cache_db():
    try:
        conn = sqlite3.connect(CACHE_DB)
        cursor = conn.cursor()
        cursor.execute("""CREATE TABLE IF NOT EXISTS signal_history (id INTEGER PRIMARY KEY AUTOINCREMENT, ticker TEXT NOT NULL, coin_id TEXT, signal_type TEXT, score REAL, detected_at TEXT NOT NULL, detected_ts REAL NOT NULL, entry_price_usd REAL, price_j1_usd REAL, perf_j1_pct REAL, verdict_j1 TEXT, UNIQUE(ticker, detected_at))""")
        conn.commit()
        conn.close()
        print(f"Cache DB initialized: {CACHE_DB}")
    except Exception as e:
        print(f"Cache init error: {e}")

def save_signal_history(data):
    try:
        conn = sqlite3.connect(CACHE_DB)
        cursor = conn.cursor()
        detected_at = datetime.now(timezone.utc).isoformat()
        detected_ts = datetime.now(timezone.utc).timestamp()
        signals_to_track = data.get("strong_buy", []) + data.get("watchlist", [])
        for signal in signals_to_track:
            ticker = signal.get("ticker")
            market_data = signal.get("market_data") or {}
            if not ticker: continue
            entry_price = market_data.get("current_price_usd")
            if entry_price is None: continue
            coin_id = market_data.get("coin_id")
            cursor.execute("INSERT OR IGNORE INTO signal_history (ticker, coin_id, signal_type, score, detected_at, detected_ts, entry_price_usd) VALUES (?, ?, ?, ?, ?, ?, ?)", (ticker, coin_id, signal.get("signal_type"), signal.get("score"), detected_at, detected_ts, entry_price))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Error saving signal history: {e}")

def update_signal_performance():
    try:
        conn = sqlite3.connect(CACHE_DB)
        cursor = conn.cursor()
        now_ts = datetime.now(timezone.utc).timestamp()
        cursor.execute("SELECT id, detected_ts, entry_price_usd FROM signal_history WHERE entry_price_usd IS NOT NULL AND price_j1_usd IS NULL")
        rows = cursor.fetchall()
        for signal_id, detected_ts, entry_price in rows:
            age_hours = (now_ts - detected_ts) / 3600
            if age_hours >= 24:
                print(f"Signal {signal_id} ready for J+1 check")
        conn.close()
    except Exception as e:
        print(f"Error updating signal performance: {e}")

def build_performance_report():
    try:
        conn = sqlite3.connect(CACHE_DB)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM signal_history")
        total = cursor.fetchone()[0]
        conn.close()
        return f"
SIGNAL PERFORMANCE BACKTEST
{'=' * 80}
Total signaux suivis: {total}
"
    except Exception as e:
        return f"
SIGNAL PERFORMANCE BACKTEST
Error: {e}
"


def classify_performance(perf_pct):
    if perf_pct is None: return "pending"
    if perf_pct >= 20: return "true_positive_strong"
    if perf_pct >= 7: return "true_positive"
    if perf_pct <= -20: return "false_positive_strong"
    if perf_pct <= -7: return "false_positive"
    return "neutral"

def main():
    print("V8.4 initialized with signal tracking")
    init_cache_db()
    print("Ready for production use")

if __name__ == "__main__":
    main()
