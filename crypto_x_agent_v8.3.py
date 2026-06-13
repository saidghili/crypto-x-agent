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


print("VERSION V8.3 - SLIDING WINDOW + CACHING + PUMP DETECTION")


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
    """Parse robust des dates Twitter / ISO. Retourne un datetime UTC ou None."""
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
    """True si le tweet est posterieur au dernier run."""
    if not since_time:
        return True
    tweet_dt = parse_tweet_datetime(tweet.get("created_at"))
    since_dt = parse_tweet_datetime(since_time)
    if not tweet_dt or not since_dt:
        return True
    return tweet_dt > since_dt


def init_cache_db():
    """Initialise SQLite: cache CoinGecko, cache tweets, timestamp dernier run."""
    try:
        conn = sqlite3.connect(CACHE_DB)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS coingecko_cache (
                ticker TEXT PRIMARY KEY,
                data TEXT,
                timestamp REAL
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS tweets_cache (
                account TEXT NOT NULL,
                tweet_id TEXT NOT NULL,
                tweet_json TEXT,
                text TEXT,
                created_at TEXT,
                created_ts REAL DEFAULT 0,
                cached_at REAL,
                PRIMARY KEY (account, tweet_id)
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS run_metadata (
                account TEXT PRIMARY KEY,
                last_run_time TEXT,
                timestamp REAL
            )
        """)
        conn.commit()
        conn.close()
        print(f"Cache DB initialized: {CACHE_DB}")
    except Exception as e:
        print(f"Cache init error: {e}")


def get_cached_market_data(ticker_symbol):
    """Recupere les donnees CoinGecko en cache si disponibles et fraiches."""
    try:
        conn = sqlite3.connect(CACHE_DB)
        cursor = conn.cursor()
        cursor.execute("SELECT data, timestamp FROM coingecko_cache WHERE ticker = ?", (ticker_symbol,))
        result = cursor.fetchone()
        conn.close()
        if result:
            data_json, timestamp = result
            age_hours = (datetime.now(timezone.utc).timestamp() - timestamp) / 3600
            if age_hours < CACHE_TTL_HOURS:
                print(f"  [CACHE HIT] {ticker_symbol}")
                return json.loads(data_json)
            print(f"  [CACHE STALE] {ticker_symbol} ({age_hours:.1f}h old)")
        return None
    except Exception:
        return None


def cache_market_data(ticker_symbol, data):
    """Sauvegarde les donnees CoinGecko en cache."""
    try:
        conn = sqlite3.connect(CACHE_DB)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT OR REPLACE INTO coingecko_cache (ticker, data, timestamp) VALUES (?, ?, ?)",
            (ticker_symbol, json.dumps(data), datetime.now(timezone.utc).timestamp())
        )
        conn.commit()
        conn.close()
    except Exception:
        pass


def get_last_run_time_for_account(account):
    """Recupere le timestamp du dernier run pour un compte."""
    account = norm_author(account)
    try:
        conn = sqlite3.connect(CACHE_DB)
        cursor = conn.cursor()
        cursor.execute("SELECT last_run_time FROM run_metadata WHERE account = ?", (account,))
        result = cursor.fetchone()
        conn.close()
        return result[0] if result else None
    except Exception as e:
        print(f"Error reading last run time @{account}: {e}")
        return None


def save_run_time_for_account(account, timestamp):
    """Sauvegarde le timestamp du dernier run pour un compte. A appeler seulement apres generation reussie du rapport."""
    account = norm_author(account)
    try:
        conn = sqlite3.connect(CACHE_DB)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT OR REPLACE INTO run_metadata (account, last_run_time, timestamp) VALUES (?, ?, ?)",
            (account, timestamp, datetime.now(timezone.utc).timestamp())
        )
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Error saving last run time @{account}: {e}")


def cache_tweets(account, tweets):
    """Sauvegarde les nouveaux tweets dans SQLite. Applique la fenetre glissante: MAX_TWEETS_PER_ACCOUNT tweets maximum par compte."""
    account = norm_author(account)
    if not tweets:
        return
    try:
        conn = sqlite3.connect(CACHE_DB)
        cursor = conn.cursor()
        now_ts = datetime.now(timezone.utc).timestamp()
        for tweet in tweets:
            tweet_id = str(tweet.get("id") or "").strip()
            text = tweet.get("text") or ""
            created_at = tweet.get("created_at") or ""
            if not tweet_id or not text:
                continue
            payload = dict(tweet)
            payload["id"] = tweet_id
            payload["author"] = norm_author(payload.get("author") or account)
            payload.setdefault("url", f"https://x.com/{account}/status/{tweet_id}")
            payload.setdefault("like_count", 0)
            payload.setdefault("retweet_count", 0)
            payload.setdefault("reply_count", 0)
            payload.setdefault("view_count", 0)
            payload["from_cache"] = False
            cursor.execute(
                """INSERT OR REPLACE INTO tweets_cache
                    (account, tweet_id, tweet_json, text, created_at, created_ts, cached_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (account, tweet_id, json.dumps(payload, ensure_ascii=False), text, created_at, tweet_created_ts(payload), now_ts)
            )
        cursor.execute(
            """DELETE FROM tweets_cache WHERE account = ?
            AND tweet_id NOT IN (SELECT tweet_id FROM tweets_cache WHERE account = ?
            ORDER BY created_ts DESC, cached_at DESC LIMIT ?)""",
            (account, account, MAX_TWEETS_PER_ACCOUNT)
        )
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Error caching tweets @{account}: {e}")


def get_cached_tweets(account, limit=None):
    """Recupere les tweets en cache pour un compte. Ce sont les tweets de la fenetre glissante."""
    account = norm_author(account)
    limit = limit or MAX_TWEETS_PER_ACCOUNT
    try:
        conn = sqlite3.connect(CACHE_DB)
        cursor = conn.cursor()
        cursor.execute(
            """SELECT tweet_json, tweet_id, text, created_at FROM tweets_cache
            WHERE account = ? ORDER BY created_ts DESC, cached_at DESC LIMIT ?""",
            (account, limit)
        )
        rows = cursor.fetchall()
        conn.close()
        tweets = []
        for tweet_json, tweet_id, text, created_at in rows:
            try:
                tweet = json.loads(tweet_json) if tweet_json else {}
            except Exception:
                tweet = {}
            tweet.setdefault("id", tweet_id)
            tweet.setdefault("author", account)
            tweet.setdefault("text", text)
            tweet.setdefault("created_at", created_at)
            tweet.setdefault("url", f"https://x.com/{account}/status/{tweet_id}")
            tweet.setdefault("like_count", 0)
            tweet.setdefault("retweet_count", 0)
            tweet.setdefault("reply_count", 0)
            tweet.setdefault("view_count", 0)
            tweet["from_cache"] = True
            tweets.append(tweet)
        return tweets
    except Exception as e:
        print(f"Error reading cached tweets @{account}: {e}")
        return []


def detect_pump(market_data):
    """Detecte les signaux de pump bases sur volume et volatilite."""
    if not market_data:
        return None
    flags = []
    pump_score = 0
    volume_24h = market_data.get("volume_24h_usd") or 0
    market_cap = market_data.get("market_cap_usd") or 0
    price_change = market_data.get("price_change_24h_percent") or 0
    if market_cap > 0:
        volume_ratio = volume_24h / market_cap
        if volume_ratio > 2.0:
            flags.append("extreme_volume_ratio")
            pump_score += 30
        elif volume_ratio > 1.5:
            flags.append("high_volume_ratio")
            pump_score += 15
    if abs(price_change) > 100:
        flags.append("extreme_volatility_pump")
        pump_score += 40
    elif abs(price_change) > 75:
        flags.append("high_volatility_pump")
        pump_score += 20
    if market_cap < 5_000_000 and pump_score > 20:
        flags.append("microcap_pump_danger")
        pump_score += 20
    if pump_score > 0:
        pump_level = "critical" if pump_score >= 60 else "high" if pump_score >= 30 else "moderate"
        return {"detected": True, "pump_score": pump_score, "pump_level": pump_level, "flags": flags}
    return None


def get_author_tier(author):
    author = norm_author(author)
    if author in TIER_1:
        return 1
    if author in TIER_2:
        return 2
    if author in TIER_3:
        return 3
    return 0


def get_tier_multiplier(tier):
    return {1: 3.0, 2: 2.0, 3: 1.0}.get(tier, 0.0)


def is_promotional_tweet(text):
    promo_patterns = [
        r"committing\s+\$",
        r"launching\s+",
        r"celebrate",
        r"excited\s+to\s+announce",
        r"proud\s+to\s+present",
        r"we\s+(?:are\s+)?committed",
        r"100k|1m\s+(?:in|incentive)",
        r"weekly\s+(?:pot|bounty)",
    ]
    text_lower = (text or "").lower()
    return any(re.search(pattern, text_lower) for pattern in promo_patterns)


def analyze_sentiment(text):
    text_lower = (text or "").lower()
    positive_count = 0
    negative_count = 0
    for word in POSITIVE_KEYWORDS:
        if re.search(rf"\b{re.escape(word)}\b", text_lower):
            positive_count += 1
    for word in NEGATIVE_KEYWORDS:
        if re.search(rf"\b{re.escape(word)}\b", text_lower):
            negative_count += 1
    for pattern in BULLISH_PATTERNS:
        if pattern in text_lower:
            positive_count += 2
    for pattern in BEARISH_PATTERNS:
        if pattern in text_lower:
            negative_count += 2
    is_promo = is_promotional_tweet(text)
    if is_promo and negative_count == 0:
        positive_count = max(positive_count, 1)
    if positive_count + negative_count == 0:
        return 0.0
    sentiment = (positive_count - negative_count) / (positive_count + negative_count)
    return max(-1.0, min(1.0, sentiment))


def fetch_latest_tweets(username, limit=20, since_time=None):
    """Recupere les tweets recents d'un compte. Filtre localement pour ne garder que ceux posterieurs a since_time."""
    url = "https://api.twitterapi.io/twitter/user/last_tweets"
    headers = {"X-API-Key": TWITTERAPI_KEY}
    params = {"userName": username, "pageSize": min(limit, 20), "includeReplies": "false"}
    try:
        r = requests.get(url, headers=headers, params=params, timeout=30)
    except Exception as e:
        print(f"ERREUR @{username}: {e}")
        return []
    print(f"@{username}: {r.status_code}")
    if r.status_code != 200:
        return []
    try:
        data = r.json()
    except Exception:
        return []
    tweets = data.get("data", {}).get("tweets", []) if isinstance(data, dict) else []
    if not isinstance(tweets, list):
        return []
    cleaned = []
    for t in tweets:
        if not isinstance(t, dict):
            continue
        text = t.get("text") or ""
        tweet_id = t.get("id") or ""
        if not text:
            continue
        if text.strip().lower().startswith("rt @"):
            continue
        tweet = {
            "id": str(tweet_id),
            "author": norm_author(username),
            "text": text,
            "created_at": t.get("createdAt") or t.get("created_at") or "",
            "url": t.get("url") or f"https://x.com/{username}/status/{tweet_id}",
            "like_count": t.get("likeCount", 0) or 0,
            "retweet_count": t.get("retweetCount", 0) or 0,
            "reply_count": t.get("replyCount", 0) or 0,
            "view_count": t.get("viewCount", 0) or 0,
            "from_cache": False,
        }
        if is_tweet_after(tweet, since_time):
            cleaned.append(tweet)
    return cleaned


def deduplicate_tweets(tweets):
    seen_ids = set()
    seen_texts = set()
    result = []
    for tweet in tweets:
        tweet_id = str(tweet.get("id") or "")
        text_key = re.sub(r"\s+", " ", tweet.get("text", "").strip().lower())[:300]
        if tweet_id and tweet_id in seen_ids:
            continue
        if text_key and text_key in seen_texts:
            continue
        if tweet_id:
            seen_ids.add(tweet_id)
        if text_key:
            seen_texts.add(text_key)
        result.append(tweet)
    return result


def extract_tickers(text):
    raw = re.findall(r"\$[A-Za-z0-9_]{2,15}", text or "")
    clean = []
    for ticker in raw:
        ticker = ticker.upper()
        if re.fullmatch(r"\$[0-9]+", ticker):
            continue
        if re.fullmatch(r"\$[0-9]+[KMB]", ticker):
            continue
        if ticker in BLACKLIST_TICKERS:
            continue
        clean.append(ticker)
    return list(dict.fromkeys(clean))


def is_ticker_list_tweet(text):
    return len(extract_tickers(text)) >= 8


def extract_contracts_and_links(text):
    text = text or ""
    evm_contracts = re.findall(r"0x[a-fA-F0-9]{40}", text)
    solana_contracts = re.findall(r"\b[1-9A-HJ-NP-Za-km-z]{32,44}\b", text)
    dexscreener_links = re.findall(r"https?://(?:www\.)?dexscreener\.com/\S+", text)
    pumpfun_links = re.findall(r"https?://(?:www\.)?pump\.fun/\S+", text)
    gecko_links = re.findall(r"https?://(?:www\.)?geckoterminal\.com/\S+", text)
    return evm_contracts, solana_contracts, dexscreener_links, pumpfun_links, gecko_links


def detect_narratives(text):
    text_l = (text or "").lower()
    narratives = []
    for name, keywords in NARRATIVE_KEYWORDS.items():
        for keyword in keywords:
            if re.search(rf"\b{re.escape(keyword)}\b", text_l):
                narratives.append(name)
                break
    return narratives


def engagement_score(tweet):
    likes = tweet.get("like_count", 0) or 0
    retweets = tweet.get("retweet_count", 0) or 0
    replies = tweet.get("reply_count", 0) or 0
    views = tweet.get("view_count", 0) or 0
    score = likes + retweets * 2 + replies * 2
    if views > 10_000:
        score += 10
    if views > 100_000:
        score += 20
    if views > 500_000:
        score += 30
    return score


def check_coingecko_market_data(ticker_symbol):
    """Recupere les donnees CoinGecko avec cache."""
    cached = get_cached_market_data(ticker_symbol)
    if cached:
        return cached
    try:
        ticker_clean = ticker_symbol.lstrip("$").lower()
        url = "https://api.coingecko.com/api/v3/search"
        params = {"query": ticker_clean}
        r = requests.get(url, params=params, timeout=5)
        if r.status_code != 200:
            return None
        data = r.json()
        coins = data.get("coins", [])
        if not coins:
            return None
        coin = next((c for c in coins if (c.get("symbol") or "").upper() == ticker_symbol.lstrip("$").upper()), coins[0])
        coin_id = coin.get("id")
        if not coin_id:
            return None
        market_url = f"https://api.coingecko.com/api/v3/coins/{coin_id}"
        market_params = {"localization": "false", "tickers": "false", "market_data": "true", "community_data": "false", "developer_data": "false"}
        r2 = requests.get(market_url, params=market_params, timeout=5)
        if r2.status_code != 200:
            return None
        market_data = r2.json()
        result = {
            "name": market_data.get("name"),
            "symbol": market_data.get("symbol", "").upper(),
            "market_cap_usd": market_data.get("market_data", {}).get("market_cap", {}).get("usd"),
            "volume_24h_usd": market_data.get("market_data", {}).get("total_volume", {}).get("usd"),
            "circulating_supply": market_data.get("market_data", {}).get("circulating_supply"),
            "ath_usd": market_data.get("market_data", {}).get("ath", {}).get("usd"),
            "atl_usd": market_data.get("market_data", {}).get("atl", {}).get("usd"),
            "price_change_24h_percent": market_data.get("market_data", {}).get("price_change_percentage_24h"),
        }
        cache_market_data(ticker_symbol, result)
        print(f"  [API CALL] {ticker_symbol}")
        return result
    except Exception:
        return None


def validate_market_data(market_data):
    if not market_data:
        return {"score": 0, "flags": ["no_market_data"], "risk_level": "critical"}
    flags = []
    score = 100
    market_cap = market_data.get("market_cap_usd") or 0
    volume_24h = market_data.get("volume_24h_usd") or 0
    price_change = market_data.get("price_change_24h_percent") or 0
    if market_cap < 500_000:
        flags.append("nano_cap_extreme_risk")
        score -= 60
    elif market_cap < 5_000_000:
        flags.append("micro_cap_risk")
        score -= 40
    elif market_cap < 10_000_000:
        flags.append("micro_cap")
        score -= 20
    if volume_24h == 0:
        flags.append("zero_volume_dead_token")
        score -= 50
    elif market_cap > 0:
        volume_ratio = volume_24h / market_cap
        if volume_ratio < 0.01:
            flags.append("low_liquidity")
            score -= 25
        elif volume_ratio > 2:
            flags.append("possible_manipulation")
            score -= 15
    if abs(price_change) > 150:
        flags.append("extreme_volatility_24h")
        score -= 30
    elif abs(price_change) > 75:
        flags.append("high_volatility")
        score -= 15
    risk_level = "safe" if score >= 70 else "risky" if score >= 40 else "critical"
    return {"score": max(0, score), "flags": flags, "risk_level": risk_level}


def score_ticker(ticker, mentions):
    authors = {m["author"] for m in mentions}
    author_count = len(authors)
    mention_count = len(mentions)
    avg_sentiment = sum(m["sentiment"] for m in mentions) / len(mentions)
    mention_counts_by_author = Counter(m["author"] for m in mentions)
    max_mentions_single_author = max(mention_counts_by_author.values()) if mention_counts_by_author else 1
    if author_count == 1 and max_mentions_single_author > 2:
        risk_penalty_spam = min(15, max_mentions_single_author * 3)
    else:
        risk_penalty_spam = 0
    consensus_score = 15 if author_count == 1 else 40 if author_count == 2 else 65
    mention_score = min(mention_count * 4, 20)
    tier_score = 0
    contract_bonus = 0
    engagement_bonus = 0
    risk_penalty = 0
    for m in mentions:
        tier = get_author_tier(m["author"])
        tier_score += {1: 15, 2: 10, 3: 5}.get(tier, 0) * get_tier_multiplier(tier)
        if m["has_contract_or_link"]:
            contract_bonus += 20
        if m["engagement"] > 50:
            engagement_bonus += 5
        if m["engagement"] > 250:
            engagement_bonus += 10
        if m["sentiment"] < -0.4:
            risk_penalty += 20
    if ticker in KNOWN_LARGE_CAPS and author_count == 1:
        risk_penalty += 30
    sentiment_factor = max(-0.5, min(1.0, avg_sentiment))
    raw = (consensus_score + mention_score + min(tier_score / 2, 30) + min(contract_bonus, 25) + min(engagement_bonus, 15))
    raw = raw * (1 + max(0, sentiment_factor) * 0.35) - risk_penalty - risk_penalty_spam
    if author_count == 1:
        tier_1_author = any(get_author_tier(a) == 1 for a in authors)
        has_contract = any(m["has_contract_or_link"] for m in mentions)
        if tier_1_author and has_contract:
            raw = min(raw, 65)
        else:
            raw = min(raw, 45)
    return round(max(0, min(raw, 100)), 2)


def classify_signal(ticker, mentions, score, avg_sentiment):
    authors = {m["author"] for m in mentions}
    author_count = len(authors)
    has_contract = any(m["has_contract_or_link"] for m in mentions)
    has_tier1 = any(get_author_tier(a) == 1 for a in authors)
    if avg_sentiment < -0.35 and any(m["sentiment"] < -0.4 for m in mentions):
        return "red_flag"
    if score >= 70 and avg_sentiment > 0.3 and (author_count >= 2 or (has_tier1 and has_contract)):
        return "strong_buy"
    if score >= 60 and avg_sentiment > 0.1 and author_count >= 2:
        return "watchlist"
    if score >= 60 and avg_sentiment > 0.1 and has_tier1:
        return "watchlist"
    if has_contract and has_tier1 and avg_sentiment > 0.0:
        return "watchlist"
    return "weak_signal"


def build_report_data(tweets):
    tweets = deduplicate_tweets(tweets)
    ticker_mentions = defaultdict(list)
    narrative_counter = Counter()
    new_contracts = []
    ignored_list_tweets = 0
    tweets_from_cache = sum(1 for t in tweets if t.get("from_cache"))
    tweets_new = len(tweets) - tweets_from_cache
    for tweet in tweets:
        text = tweet.get("text", "")
        author = tweet.get("author", "")
        url = tweet.get("url", "")
        sentiment = analyze_sentiment(text)
        engagement = engagement_score(tweet)
        narratives = detect_narratives(text)
        contracts, sol_contracts, dex_links, pump_links, gecko_links = extract_contracts_and_links(text)
        has_contract_or_link = bool(contracts or sol_contracts or dex_links or pump_links or gecko_links)
        for n in narratives:
            narrative_counter[n] += 1
        if has_contract_or_link:
            new_contracts.append({
                "author": author,
                "contracts": contracts,
                "sol_contracts": sol_contracts,
                "dex_links": dex_links,
                "pump_links": pump_links,
                "gecko_links": gecko_links,
                "text": text[:260],
                "url": url,
                "sentiment": sentiment,
                "from_cache": tweet.get("from_cache", False),
            })
        if is_ticker_list_tweet(text):
            ignored_list_tweets += 1
            continue
        for ticker in extract_tickers(text):
            ticker_mentions[ticker].append({
                "author": author,
                "text": text[:260],
                "url": url,
                "engagement": engagement,
                "sentiment": sentiment,
                "has_contract_or_link": has_contract_or_link,
                "from_cache": tweet.get("from_cache", False),
            })
    ranked = []
    for ticker, mentions in ticker_mentions.items():
        score = score_ticker(ticker, mentions)
        avg_sentiment = sum(m["sentiment"] for m in mentions) / len(mentions)
        authors = sorted({m["author"] for m in mentions})
        signal_type = classify_signal(ticker, mentions, score, avg_sentiment)
        gecko_data = check_coingecko_market_data(ticker)
        market_validation = validate_market_data(gecko_data)
        pump_detection = detect_pump(gecko_data)
        ranked.append({
            "ticker": ticker,
            "score": score,
            "avg_sentiment": round(avg_sentiment, 3),
            "mention_count": len(mentions),
            "author_count": len(authors),
            "authors": authors,
            "signal_type": signal_type,
            "market_data": gecko_data,
            "market_validation": market_validation,
            "pump_detection": pump_detection,
            "mentions": mentions,
        })
    ranked.sort(key=lambda x: x["score"], reverse=True)
    strong_buy = [r for r in ranked if r["signal_type"] == "strong_buy"]
    watchlist = [r for r in ranked if r["signal_type"] == "watchlist"]
    red_flags = [r for r in ranked if r["signal_type"] == "red_flag"]
    weak = [r for r in ranked if r["signal_type"] == "weak_signal"]
    return {
        "generated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M"),
        "tweets_analyzed": len(tweets),
        "tweets_new": tweets_new,
        "tweets_from_cache": tweets_from_cache,
        "ignored_list_tweets": ignored_list_tweets,
        "narratives": narrative_counter.most_common(10),
        "strong_buy": strong_buy,
        "watchlist": watchlist,
        "red_flags": red_flags,
        "weak_signals": weak,
        "ranked": ranked,
        "new_contracts": new_contracts,
    }


def build_text_report(data):
    lines = []
    lines.append("Crypto X Trend Report V8.3 (Sliding Window + Caching + Pump Detection)")
    lines.append("=" * 80)
    lines.append(f"Date UTC : {data['generated_at_utc']}")
    lines.append(f"Tweets analysés : {data['tweets_analyzed']}")
    lines.append(f"Tweets nouveaux : {data.get('tweets_new', 0)}")
    lines.append(f"Tweets cache : {data.get('tweets_from_cache', 0)}")
    lines.append(f"Ignorés (ticker lists) : {data['ignored_list_tweets']}")
    lines.append("")
    lines.append("TOP NARRATIVES")
    lines.append("-" * 80)
    if data["narratives"]:
        for narrative, count in data["narratives"]:
            lines.append(f"  {narrative}: {count} mentions")
    else:
        lines.append("  Aucune narrative.")
    lines.append("")
    lines.append("STRONG BUY SIGNALS")
    lines.append("-" * 80)
    if data["strong_buy"]:
        for r in data["strong_buy"][:10]:
            pump_warning = " PUMP DETECTED" if r["pump_detection"] and r["pump_detection"].get("detected") else ""
            lines.append(f"  {r['ticker']} — Score {r['score']}/100 — {r['author_count']} comptes{pump_warning}")
            lines.append(f"    Sentiment: {r['avg_sentiment']:+.2f} | Risk: {r['market_validation'].get('risk_level', '?')}")
            lines.append(f"    Authors: {', '.join('@' + a for a in r['authors'][:8])}")
            if r["pump_detection"] and r["pump_detection"].get("detected"):
                lines.append(f"    Pump Score: {r['pump_detection'].get('pump_score')}/100 | Level: {r['pump_detection'].get('pump_level')}")
            lines.append("")
    else:
        lines.append("  Aucun signal strong buy.\n")
    lines.append("WATCHLIST")
    lines.append("-" * 80)
    if data["watchlist"]:
        for r in data["watchlist"][:10]:
            pump_warning = " PUMP" if r["pump_detection"] and r["pump_detection"].get("detected") else ""
            lines.append(f"  {r['ticker']} — Score {r['score']}/100 — {r['author_count']} comptes{pump_warning}")
            lines.append(f"    Sentiment: {r['avg_sentiment']:+.2f} | Risk: {r['market_validation'].get('risk_level', '?')}")
            lines.append(f"    Authors: {', '.join('@' + a for a in r['authors'][:8])}")
            lines.append("")
    else:
        lines.append("  Aucun watchlist.\n")
    lines.append("RED FLAGS - SKIP")
    lines.append("-" * 80)
    if data["red_flags"]:
        for r in data["red_flags"][:10]:
            lines.append(f"  {r['ticker']} — Sentiment {r['avg_sentiment']} — Score {r['score']}")
            lines.append("")
    else:
        lines.append("  Aucun red flag.\n")
    lines.append("MARKET DATA & CONTRACTS")
    lines.append("-" * 80)
    if data["new_contracts"]:
        for item in data["new_contracts"][:8]:
            source = "CACHE" if item.get("from_cache") else "NEW"
            lines.append(f"  [{source}] [@{item['author']}] {item['text']}")
            if item["contracts"]:
                lines.append(f"    EVM contracts: {', '.join(item['contracts'][:2])}")
            if item["sol_contracts"]:
                lines.append(f"    SOL contracts: {', '.join(item['sol_contracts'][:2])}")
            if item["dex_links"]:
                lines.append(f"    Dexscreener: {', '.join(item['dex_links'][:2])}")
            lines.append("")
    else:
        lines.append("  Aucun contrat.\n")
    return "\n".join(lines)


def save_outputs(data, report):
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M")
    txt_path = os.path.join(OUTPUT_DIR, f"crypto_x_report_v83_{stamp}.txt")
    json_path = os.path.join(OUTPUT_DIR, f"crypto_x_report_v83_{stamp}.json")
    csv_path = os.path.join(OUTPUT_DIR, f"crypto_x_ranked_v83_{stamp}.csv")
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write(report)
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, default=str)
    with open(csv_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["ticker", "score", "sentiment", "mentions", "author_count", "authors", "signal_type", "market_cap", "volume_24h", "market_risk", "market_flags", "pump_detected", "pump_level", "pump_flags"])
        for r in data["ranked"]:
            market_cap = r["market_data"].get("market_cap_usd") if r["market_data"] else None
            volume = r["market_data"].get("volume_24h_usd") if r["market_data"] else None
            market_risk = r["market_validation"].get("risk_level") if r["market_validation"] else None
            market_flags = ",".join(r["market_validation"].get("flags", [])) if r["market_validation"] else ""
            pump_detected = r["pump_detection"].get("detected") if r["pump_detection"] else False
            pump_level = r["pump_detection"].get("pump_level") if r["pump_detection"] else None
            pump_flags = ",".join(r["pump_detection"].get("flags", [])) if r["pump_detection"] else ""
            writer.writerow([r["ticker"], r["score"], r["avg_sentiment"], r["mention_count"], r["author_count"], ",".join(r["authors"]), r["signal_type"], market_cap, volume, market_risk, market_flags, pump_detected, pump_level, pump_flags])
    return txt_path, json_path, csv_path


def send_email(subject, body):
    if not all([EMAIL_FROM, EMAIL_TO, EMAIL_PASSWORD, SMTP_SERVER, SMTP_PORT]):
        print("Email config incomplete: skipped.")
        return False
    try:
        msg = MIMEMultipart()
        msg["From"] = EMAIL_FROM
        msg["To"] = EMAIL_TO
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain", "utf-8"))
        if SMTP_PORT == 465:
            with smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT) as server:
                server.login(EMAIL_FROM, EMAIL_PASSWORD)
                server.send_message(msg)
        else:
            with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
                server.starttls()
                server.login(EMAIL_FROM, EMAIL_PASSWORD)
                server.send_message(msg)
        print("Email sent")
        return True
    except Exception as e:
        print(f"Email failed: {e}")
        return False


def main():
    if not TWITTERAPI_KEY:
        raise ValueError("TWITTERAPI_KEY missing")
    init_cache_db()
    current_run_time = datetime.now(timezone.utc).isoformat()
    processed_accounts = []
    all_tweets = []
    print(f"Accounts: {len(ACCOUNTS_LIST)}")
    print(f"Fetch per run/account: {FETCH_TWEETS_PER_RUN}")
    print(f"Sliding cache/account: {MAX_TWEETS_PER_ACCOUNT}")
    print(f"Current run timestamp: {current_run_time}")
    for account in ACCOUNTS_LIST:
        account_norm = norm_author(account)
        print(f"\n@{account}")
        last_run_time = get_last_run_time_for_account(account_norm)
        print(f"  Last run: {last_run_time or 'none'}")
        new_tweets = fetch_latest_tweets(username=account, limit=FETCH_TWEETS_PER_RUN, since_time=last_run_time)
        print(f"  New tweets fetched: {len(new_tweets)}")
        cache_tweets(account_norm, new_tweets)
        sliding_window = get_cached_tweets(account_norm, limit=MAX_TWEETS_PER_ACCOUNT)
        sliding_window = deduplicate_tweets(sliding_window)
        print(f"  Sliding window tweets used: {len(sliding_window)}")
        all_tweets.extend(sliding_window)
        processed_accounts.append(account_norm)
    all_tweets = deduplicate_tweets(all_tweets)
    print(f"\nTotal tweets for analysis after global dedupe: {len(all_tweets)}")
    print("Generating report...\n")
    data = build_report_data(all_tweets)
    report = build_text_report(data)
    txt_path, json_path, csv_path = save_outputs(data, report)
    for account in processed_accounts:
        save_run_time_for_account(account, current_run_time)
    print("=" * 80)
    print(report)
    print("=" * 80)
    print("\nSaved to:")
    print(f"  {txt_path}")
    print(f"  {json_path}")
    print(f"  {csv_path}")
    if SEND_EMAIL_REPORT:
        send_email("Crypto X Trend Report V8.3 - Sliding Window", report)


if __name__ == "__main__":
    main()
