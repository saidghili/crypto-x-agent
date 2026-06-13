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


print("VERSION V8.4 - SLIDING WINDOW + CACHING + PUMP DETECTION")


# =========================
# CONFIG
# =========================

TWITTERAPI_KEY = os.getenv("TWITTERAPI_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

EMAIL_FROM = os.getenv("EMAIL_FROM")
EMAIL_TO = os.getenv("EMAIL_TO")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")
SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.laposte.net")
SMTP_PORT = int(os.getenv("SMTP_PORT", "465"))

OUTPUT_DIR = os.getenv("OUTPUT_DIR", "reports")

FETCH_TWEETS_PER_RUN = int(os.getenv("FETCH_TWEETS_PER_RUN", "20"))
MAX_TWEETS_PER_ACCOUNT = int(os.getenv("MAX_TWEETS_PER_ACCOUNT", "100"))

SEND_EMAIL_REPORT = os.getenv("SEND_EMAIL_REPORT", "false").lower() == "true"
USE_GPT_SYNTHESIS = os.getenv("USE_GPT_SYNTHESIS", "true").lower() == "true"
GPT_MODEL = os.getenv("GPT_MODEL", "gpt-4-turbo")

CACHE_DB = os.getenv("CACHE_DB", "crypto_cache.db")
CACHE_TTL_HOURS = int(os.getenv("CACHE_TTL_HOURS", "6"))


ACCOUNTS_LIST = [
    "BigCheds", "CryptoMichNL", "Sheldino_D", "blknoiz06", "LarpVonTrier",
    "CrashiusClay69", "cobie", "SolBigBrain", "Austin_Federa", "weremeow",
    "Virtuals_io", "DegenSpartan", "MilesDeutscher", "DefiIgnas", "TheDeFinvestor",
    "lookonchain", "nansen_ai", "DefiLlama", "zachxbt", "jessepollak",
    "0xngmi", "Route2FI", "HopiumPapi", "AltcoinSherpa", "HsakaTrades",
    "rektfencer", "Pentosh1", "TheFlowHorse", "ByzGeneral", "CryptoHayes",
    "CL207", "RunnerXBT", "MuroCrypto"
]


TIER_1 = {x.lower() for x in {
    "cobie", "zachxbt", "CryptoHayes", "jessepollak",
    "blknoiz06", "HsakaTrades", "CL207", "Pentosh1"
}}

TIER_2 = {x.lower() for x in {
    "DegenSpartan", "nansen_ai", "0xngmi", "lookonchain",
    "MilesDeutscher", "SolBigBrain", "weremeow", "Virtuals_io",
    "DefiLlama", "DefiIgnas", "TheFlowHorse", "Route2FI"
}}

TIER_3 = {x.lower() for x in {
    "CryptoMichNL", "CrashiusClay69", "BigCheds",
    "AltcoinSherpa", "Austin_Federa", "ByzGeneral",
    "Sheldino_D", "LarpVonTrier", "TheDeFinvestor", "HopiumPapi",
    "rektfencer", "RunnerXBT", "MuroCrypto"
}}

ANTI_SCAM_ACCOUNTS = {"zachxbt"}


POSITIVE_KEYWORDS = {
    "bullish", "accumulate", "loading", "buy", "buying", "strong", "upside",
    "breakout", "support", "holding", "long", "pump", "moon", "gem", "alpha",
    "early", "opportunity", "entry", "dip", "accumulation", "going higher",
    "outperform", "undervalued", "setup", "catalysts", "loaded", "cheap",
    "reversal", "confirmation", "strength", "bullish momentum", "oversold", "bounce",
    "recovery", "rally", "gaining", "momentum", "positive", "excited"
}

NEGATIVE_KEYWORDS = {
    "rug", "scam", "hack", "exploit", "honeypot", "warning", "avoid",
    "manipulation", "suspicious", "malicious", "attack", "vulnerable",
    "breach", "fraud", "beware", "caution", "dead", "failed", "collapse"
}

BULLISH_PATTERNS = {
    "buying the dip", "loaded on", "accumulating", "stacking", "loading up",
    "accumulation zone", "buying pressure", "support bounce", "oversold bounce",
    "cheap entry", "looks ready", "send it"
}

BEARISH_PATTERNS = {
    "exit position", "sold out", "leaving position", "warning sign", "be careful",
    "stay away", "do not buy", "don't buy", "avoid this", "looks dead"
}

NARRATIVE_KEYWORDS = {
    "AI / AI Agents": ["ai agents", "virtuals", "deai", "autonomous agents", "eliza"],
    "Memecoin": ["memecoin", "memecoins", "degen", "degens"],
    "Solana": ["solana", "pump.fun", "jupiter", "bonk"],
    "Base": ["base", "brett", "toshi", "buildonbase"],
    "RWA": ["rwa", "tokenization", "tokenized", "treasury", "ondo"],
    "DePIN": ["depin"],
    "DeFi": ["defi", "yield", "perps", "dex", "liquidity", "lending", "lsd"],
    "Restaking": ["restaking", "eigen", "eigenlayer"],
    "Gaming": ["gamefi", "play-to-earn", "p2e"],
}


BLACKLIST_TICKERS = {
    "$USD", "$USDT", "$USDC", "$BTC", "$ETH",
    "$SPY", "$QQQ", "$DIA", "$IWM", "$VIX",
    "$XAU", "$XAG", "$GOLD", "$SILVER", "$OIL",
    "$ORCL", "$SMCI", "$CPB", "$TSLA", "$AAPL",
    "$MSFT", "$GOOGL", "$GOOG", "$AMZN", "$META",
    "$NVDA", "$NFLX", "$AMD", "$INTC", "$PLTR",
    "$MSTR", "$COIN", "$HOOD", "$NKE", "$DIS",
    "$K", "$M", "$B", "$A", "$C", "$D", "$I", "$O", "$X", "$Z",
    "$SPX", "$IXIC", "$RUT", "$DXY",
    "$MU", "$EWY", "$GLD", "$SLV",
    "$RAVE"
}

KNOWN_LARGE_CAPS = {
    "$SOL", "$BNB", "$XRP", "$DOGE", "$ADA", "$AVAX",
    "$LINK", "$AAVE", "$SUI", "$TRX", "$XMR", "$ZEC",
    "$NEAR", "$PEPE", "$SHIB", "$FLOKI", "$ARB", "$OP",
    "$INJ", "$APT", "$DOT", "$LTC", "$BCH", "$TON",
    "$UNI", "$MKR", "$RNDR", "$RENDER", "$FET", "$TAO",
    "$ONDO", "$PENDLE", "$SEI", "$TIA", "$JUP", "$WIF",
    "$BONK"
}


def norm_author(author: str) -> str:
    return (author or "").replace("@", "").strip().lower()


def parse_tweet_datetime(value):
    if not value:
        return None
    value = str(value).strip()
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        pass
    try:
        dt = datetime.strptime(value, "%a %b %d %H:%M:%S %z %Y")
        return dt.astimezone(timezone.utc)
    except Exception:
        pass
    return None


def tweet_created_ts(tweet):
    dt = parse_tweet_datetime(tweet.get("created_at"))
    return dt.timestamp() if dt else 0.0


def is_tweet_after(tweet, since_time):
    if not since_time:
        return True
    tweet_dt = parse_tweet_datetime(tweet.get("created_at"))
    since_dt = parse_tweet_datetime(since_time)
    if not tweet_dt or not since_dt:
        return True
    return tweet_dt > since_dt
