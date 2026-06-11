import os
import re
import smtplib
import requests
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timezone, timedelta
from collections import defaultdict, Counter


TWITTERAPI_KEY = os.getenv("TWITTERAPI_KEY")
EMAIL_FROM = os.getenv("EMAIL_FROM")
EMAIL_TO = os.getenv("EMAIL_TO")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")
SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))


EARLY_ALPHA = {
    "Ansem", "blknoiz06", "LarpVonTrier", "Poe_Ether",
    "CrashiusClay69", "theunipcs", "HopiumPapi"
}

ONCHAIN = {
    "lookonchain", "ArkhamIntel", "nansen_ai", "DefiLlama", "ScopeProtocol"
}

ANTI_SCAM = {
    "zachxbt"
}

NARRATIVE_KEYWORDS = {
    "AI / AI Agents": ["ai", "agent", "agents", "virtuals", "deai"],
    "Memecoin": ["meme", "memecoin", "memecoins", "pump", "degen"],
    "Solana": ["solana", "sol", "pumpfun", "jupiter"],
    "Base": ["base", "brett", "toshi"],
    "RWA": ["rwa", "tokenization", "tokenized", "treasury", "ondo"],
    "DePIN": ["depin"],
    "DeFi": ["defi", "yield", "perps", "dex"],
    "Restaking": ["restaking", "eigen", "eigenlayer"],
}


def load_accounts(path="accounts.txt"):
    with open(path, "r", encoding="utf-8") as f:
        accounts = []
        for line in f:
            account = line.strip().replace("@", "")
            if account:
                accounts.append(account)
    return list(dict.fromkeys(accounts))


def fetch_latest_tweets(username, limit=20):
    url = "https://api.twitterapi.io/twitter/user/latest_tweets"
    headers = {"X-API-Key": TWITTERAPI_KEY}
    params = {
        "userName": username,
        "pageSize": min(limit, 20),
        "includeReplies": False
    }

    r = requests.get(url, headers=headers, params=params, timeout=30)
    if r.status_code != 200:
        print(f"Erreur API pour {username}: {r.status_code} - {r.text[:300]}")
        return []

    data = r.json()

    tweets = data.get("tweets") or data.get("data") or []
    if isinstance(tweets, dict):
        tweets = tweets.get("tweets", [])

    cleaned = []
    for t in tweets:
        text = t.get("text") or t.get("content") or ""
        created_at = t.get("createdAt") or t.get("created_at") or ""
        tweet_id = t.get("id") or t.get("tweetId") or ""

        cleaned.append({
            "id": tweet_id,
            "author": username,
            "text": text,
            "created_at": created_at,
            "url": f"https://x.com/{username}/status/{tweet_id}" if tweet_id else ""
        })

    return cleaned


def extract_tickers(text):
    tickers = re.findall(r"\$[A-Za-z]{2,10}", text)
    blacklist = {"$USD", "$USDT", "$USDC", "$BTC", "$ETH"}
    return [t.upper() for t in tickers if t.upper() not in blacklist]


def extract_contracts_and_links(text):
    evm_contracts = re.findall(r"0x[a-fA-F0-9]{40}", text)
    dexscreener_links = re.findall(r"https?://(?:www\.)?dexscreener\.com/\S+", text)
    return evm_contracts, dexscreener_links


def detect_narratives(text):
    text_l = text.lower()
    found = []
    for narrative, keywords in NARRATIVE_KEYWORDS.items():
        if any(k in text_l for k in keywords):
            found.append(narrative)
    return found


def score_ticker(ticker, mentions):
    score = 0
    authors = {m["author"] for m in mentions}

    score += min(len(authors) * 20, 60)

    for m in mentions:
        if m["author"] in EARLY_ALPHA:
            score += 15
        if m["author"] in ONCHAIN:
            score += 10
        if m["contracts"] or m["dex_links"]:
            score += 15
        if m["author"] in ANTI_SCAM:
            score -= 30

    return max(0, min(score, 100))


def build_report(tweets):
    ticker_mentions = defaultdict(list)
    narrative_counter = Counter()
    new_contracts = []

    for tweet in tweets:
        text = tweet["text"]
        tickers = extract_tickers(text)
        narratives = detect_narratives(text)
        contracts, dex_links = extract_contracts_and_links(text)

        for n in narratives:
            narrative_counter[n] += 1

        if contracts or dex_links:
            new_contracts.append({
                "author": tweet["author"],
                "contracts": contracts,
                "dex_links": dex_links,
                "text": text[:220],
                "url": tweet["url"]
            })

        for ticker in tickers:
            ticker_mentions[ticker].append({
                "author": tweet["author"],
                "text": text[:220],
                "url": tweet["url"],
                "contracts": contracts,
                "dex_links": dex_links,
            })

    lines = []
    lines.append("Crypto X Trend Report")
    lines.append("=" * 50)
    lines.append(f"Date UTC : {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')}")
    lines.append(f"Tweets analysés : {len(tweets)}")
    lines.append("")

    lines.append("TOP NARRATIVES")
    lines.append("-" * 50)
    if narrative_counter:
        for narrative, count in narrative_counter.most_common(10):
            lines.append(f"- {narrative}: {count} mentions")
    else:
        lines.append("Aucune narrative forte détectée.")
    lines.append("")

    lines.append("TOP TICKERS")
    lines.append("-" * 50)
    if ticker_mentions:
        ranked = []
        for ticker, mentions in ticker_mentions.items():
            ranked.append((ticker, score_ticker(ticker, mentions), mentions))

        ranked.sort(key=lambda x: x[1], reverse=True)

        for ticker, score, mentions in ranked[:15]:
            authors = sorted({m["author"] for m in mentions})
            lines.append(f"{ticker} — Score {score}/100 — {len(mentions)} mentions — Comptes: {', '.join(authors)}")
            for m in mentions[:3]:
                lines.append(f"  • @{m['author']}: {m['text']}")
                if m["url"]:
                    lines.append(f"    {m['url']}")
            lines.append("")
    else:
        lines.append("Aucun cashtag détecté.")
    lines.append("")

    lines.append("CONTRATS / LIENS DEXSCREENER DETECTES")
    lines.append("-" * 50)
    if new_contracts:
        for item in new_contracts[:10]:
            lines.append(f"@{item['author']}: {item['text']}")
            if item["contracts"]:
                lines.append(f"  Contrats: {', '.join(item['contracts'])}")
            if item["dex_links"]:
                lines.append(f"  DexScreener: {', '.join(item['dex_links'])}")
            if item["url"]:
                lines.append(f"  Tweet: {item['url']}")
            lines.append("")
    else:
        lines.append("Aucun contrat ou lien DexScreener détecté.")

    return "\n".join(lines)


def send_email(subject, body):
    if not all([EMAIL_FROM, EMAIL_TO, EMAIL_PASSWORD]):
        raise ValueError("Secrets email manquants : EMAIL_FROM, EMAIL_TO ou EMAIL_PASSWORD")

    msg = MIMEMultipart()
    msg["From"] = EMAIL_FROM
    msg["To"] = EMAIL_TO
    msg["Subject"] = subject

    msg.attach(MIMEText(body, "plain", "utf-8"))

    with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
        server.starttls()
        server.login(EMAIL_FROM, EMAIL_PASSWORD)
        server.send_message(msg)


def main():
    if not TWITTERAPI_KEY:
        raise ValueError("TWITTERAPI_KEY manquant dans les secrets GitHub")

    accounts = load_accounts()
    print(f"Comptes chargés : {len(accounts)}")

    all_tweets = []
    for account in accounts:
        tweets = fetch_latest_tweets(account, limit=20)
        print(f"{account}: {len(tweets)} tweets")
        all_tweets.extend(tweets)

    report = build_report(all_tweets)
    print(report)

    subject = "Crypto X Trend Report"
    send_email(subject, report)
    print("Email envoyé.")


if __name__ == "__main__":
    main()
