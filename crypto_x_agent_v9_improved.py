import os, re, csv, json, sqlite3, smtplib, requests
from datetime import datetime, timezone
from collections import defaultdict, Counter
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

try:
    from textblob import TextBlob
    NLP_AVAILABLE = True
except ImportError:
    NLP_AVAILABLE = False

print("VERSION V9.0 - CRYPTO X AGENT")

TWITTERAPI_KEY = os.getenv("TWITTERAPI_KEY")
EMAIL_FROM = os.getenv("EMAIL_FROM")
EMAIL_TO = os.getenv("EMAIL_TO")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")
SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.laposte.net")
SMTP_PORT = int(os.getenv("SMTP_PORT", "465"))
OUTPUT_DIR = os.getenv("OUTPUT_DIR", "reports")
MAX_TWEETS_PER_ACCOUNT = int(os.getenv("MAX_TWEETS_PER_ACCOUNT", "20"))
SEND_EMAIL_REPORT = os.getenv("SEND_EMAIL_REPORT", "false").lower() == "true"

ACCOUNTS_LIST = ["BigCheds", "CryptoMichNL", "Sheldino_D", "blknoiz06", "cobie", "SolBigBrain", "Austin_Federa", "Virtuals_io", "DegenSpartan", "MilesDeutscher", "DefiIgnas", "lookonchain", "nansen_ai", "DefiLlama", "zachxbt", "jessepollak", "0xngmi", "Route2FI", "AltcoinSherpa", "HsakaTrades", "Pentosh1", "CryptoHayes", "CL207", "RunnerXBT"]

def fetch_latest_tweets(username, limit=20):
    url = "https://api.twitterapi.io/twitter/user/last_tweets"
    headers = {"X-API-Key": TWITTERAPI_KEY}
    params = {"userName": username, "pageSize": min(limit, 20), "includeReplies": "false"}
    try:
        r = requests.get(url, headers=headers, params=params, timeout=30)
        if r.status_code != 200: return []
        data = r.json()
        tweets = data.get("data", {}).get("tweets", []) if isinstance(data, dict) else []
        cleaned = []
        for t in tweets:
            if not isinstance(t, dict): continue
            text = t.get("text") or ""
            if not text or text.strip().lower().startswith("rt @"): continue
            cleaned.append({"author": username.lower(), "text": text, "created_at": t.get("createdAt", "")})
        return cleaned
    except: return []

def extract_tickers(text):
    raw = re.findall(r"\$[A-Za-z0-9_]{2,15}", text or "")
    clean = [t.upper() for t in raw if t.upper() not in {"$USD", "$USDT", "$USDC", "$BTC", "$ETH", "$SPY"}]
    return list(dict.fromkeys(clean))

def analyze_sentiment(text):
    pos_words = {"bullish", "buy", "pump", "moon", "strong", "accumulate", "loading"}
    neg_words = {"rug", "scam", "warning", "avoid", "dead"}
    text_lower = (text or "").lower()
    pos = sum(1 for w in pos_words if w in text_lower)
    neg = sum(1 for w in neg_words if w in text_lower)
    return (pos - neg) / (pos + neg) if (pos + neg) > 0 else 0

def build_report(tweets):
    ticker_mentions = defaultdict(list)
    for tweet in tweets:
        sentiment = analyze_sentiment(tweet["text"])
        for ticker in extract_tickers(tweet["text"]):
            ticker_mentions[ticker].append({"author": tweet["author"], "sentiment": sentiment})
    
    ranked = []
    for ticker, mentions in sorted(ticker_mentions.items(), key=lambda x: len(x[1]), reverse=True)[:20]:
        if len(mentions) >= 2:
            score = min(100, len(mentions) * 15)
            avg_sentiment = sum(m["sentiment"] for m in mentions) / len(mentions)
            ranked.append(f"{ticker} - Score: {score}/100 | Mentions: {len(mentions)} | Sentiment: {avg_sentiment:+.2f}")
    
    report = "Crypto X Trend Report V9.0\n" + "="*80 + f"\nDate: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}\n\nTOP SIGNALS\n" + "-"*80 + "\n" + "\n".join(ranked)
    return report

def send_email(subject, body):
    if not all([EMAIL_FROM, EMAIL_TO, EMAIL_PASSWORD]): return False
    try:
        msg = MIMEMultipart()
        msg["From"] = EMAIL_FROM
        msg["To"] = EMAIL_TO
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain", "utf-8"))
        with smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT) as server:
            server.login(EMAIL_FROM, EMAIL_PASSWORD)
            server.send_message(msg)
        print("✓ Email sent")
        return True
    except Exception as e:
        print(f"Email error: {e}")
        return False

def main():
    if not TWITTERAPI_KEY: raise ValueError("TWITTERAPI_KEY missing")
    print(f"Fetching {len(ACCOUNTS_LIST)} accounts...")
    all_tweets = []
    for account in ACCOUNTS_LIST:
        tweets = fetch_latest_tweets(account, limit=MAX_TWEETS_PER_ACCOUNT)
        all_tweets.extend(tweets)
    print(f"Total tweets: {len(all_tweets)}")
    report = build_report(all_tweets)
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M")
    with open(f"{OUTPUT_DIR}/crypto_report_{stamp}.txt", "w") as f:
        f.write(report)
    print(report)
    if SEND_EMAIL_REPORT:
        send_email("Crypto X Trend Report V9.0", report)

if __name__ == "__main__":
    main()
