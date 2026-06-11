import os
import re
import smtplib
import requests
from datetime import datetime, timezone
from collections import defaultdict, Counter
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart


print("VERSION COMPLETE TWITTERAPI.IO + EMAIL LAPOSTE - 2026-06-11")

TWITTERAPI_KEY = os.getenv("TWITTERAPI_KEY")

EMAIL_FROM = os.getenv("EMAIL_FROM")
EMAIL_TO = os.getenv("EMAIL_TO")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")
SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.laposte.net")
SMTP_PORT = int(os.getenv("SMTP_PORT", "465"))


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
    url = "https://api.twitterapi.io/twitter/user/last_tweets"

    headers = {
        "X-API-Key": TWITTERAPI_KEY
    }

    params = {
        "userName": username,
        "pageSize": min(limit, 20),
        "includeReplies": "false"
    }

    try:
        r = requests.get(url, headers=headers, params=params, timeout=30)
    except Exception as e:
        print(f"ERREUR REQUETE @{username}: {e}")
        return []

    print(f"STATUS @{username}: {r.status_code}")

    if r.status_code != 200:
        print(f"REPONSE ERREUR @{username}: {r.text[:500]}")
        return []

    try:
        data = r.json()
    except Exception as e:
        print(f"ERREUR JSON @{username}: {e}")
        print(r.text[:500])
        return []

    tweets = []

    if (
        isinstance(data, dict)
        and "data" in data
        and isinstance(data["data"], dict)
        and "tweets" in data["data"]
        and isinstance(data["data"]["tweets"], list)
    ):
        tweets = data["data"]["tweets"]
    else:
        print(f"FORMAT INATTENDU @{username}: {str(data)[:500]}")
        return []

    cleaned = []

    for t in tweets:
        if not isinstance(t, dict):
            continue

        text = t.get("text") or ""
        tweet_id = t.get("id") or ""
        created_at = t.get("createdAt") or ""
        url = t.get("url") or f"https://x.com/{username}/status/{tweet_id}"

        if text:
            cleaned.append({
                "id": tweet_id,
                "author": username,
                "text": text,
                "created_at": created_at,
                "url": url,
                "like_count": t.get("likeCount", 0),
                "retweet_count": t.get("retweetCount", 0),
                "reply_count": t.get("replyCount", 0),
                "view_count": t.get("viewCount", 0),
            })

    return cleaned


def extract_tickers(text):
    tickers = re.findall(r"\$[A-Za-z]{2,10}", text)

blacklist = {
    "$USD", "$USDT", "$USDC", "$BTC", "$ETH",
    "$SPY", "$QQQ", "$DIA", "$IWM",
    "$XAU", "$XAG", "$GOLD", "$SILVER",
    "$ORCL", "$SMCI", "$CPB", "$TSLA", "$AAPL",
    "$MSFT", "$GOOGL", "$AMZN", "$META", "$NVDA"
}

    return [t.upper() for t in tickers if t.upper() not in blacklist]


def extract_contracts_and_links(text):
    evm_contracts = re.findall(r"0x[a-fA-F0-9]{40}", text)
    dexscreener_links = re.findall(r"https?://(?:www\.)?dexscreener\.com/\S+", text)
    pumpfun_links = re.findall(r"https?://(?:www\.)?pump\.fun/\S+", text)
    geckoterminal_links = re.findall(r"https?://(?:www\.)?geckoterminal\.com/\S+", text)

    return evm_contracts, dexscreener_links, pumpfun_links, geckoterminal_links


def detect_narratives(text):
    text_l = text.lower()
    found = []

    for narrative, keywords in NARRATIVE_KEYWORDS.items():
        if any(k in text_l for k in keywords):
            found.append(narrative)

    return found


def engagement_score(tweet):
    likes = tweet.get("like_count", 0) or 0
    retweets = tweet.get("retweet_count", 0) or 0
    replies = tweet.get("reply_count", 0) or 0
    views = tweet.get("view_count", 0) or 0

    score = likes + retweets * 2 + replies * 2

    if views and views > 10000:
        score += 10
    if views and views > 100000:
        score += 20

    return score


def score_ticker(ticker, mentions):
    score = 0
    authors = {m["author"] for m in mentions}

    score += min(len(authors) * 20, 60)

    for m in mentions:
        author = m["author"]

        if author in EARLY_ALPHA:
            score += 15

        if author in ONCHAIN:
            score += 10

        if m["contracts"] or m["dex_links"] or m["pump_links"] or m["gecko_links"]:
            score += 15

        if author in ANTI_SCAM:
            score -= 30

        if m["engagement"] > 50:
            score += 5

        if m["engagement"] > 200:
            score += 10

    return max(0, min(score, 100))


def build_report(tweets):
    ticker_mentions = defaultdict(list)
    narrative_counter = Counter()
    new_contracts = []

    for tweet in tweets:
        text = tweet["text"]

        tickers = extract_tickers(text)
        narratives = detect_narratives(text)
        contracts, dex_links, pump_links, gecko_links = extract_contracts_and_links(text)
        engagement = engagement_score(tweet)

        for n in narratives:
            narrative_counter[n] += 1

        if contracts or dex_links or pump_links or gecko_links:
            new_contracts.append({
                "author": tweet["author"],
                "contracts": contracts,
                "dex_links": dex_links,
                "pump_links": pump_links,
                "gecko_links": gecko_links,
                "text": text[:240],
                "url": tweet["url"]
            })

        for ticker in tickers:
            ticker_mentions[ticker].append({
                "author": tweet["author"],
                "text": text[:240],
                "url": tweet["url"],
                "contracts": contracts,
                "dex_links": dex_links,
                "pump_links": pump_links,
                "gecko_links": gecko_links,
                "engagement": engagement,
            })

    lines = []
    lines.append("Crypto X Trend Report")
    lines.append("=" * 60)
    lines.append(f"Date UTC : {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')}")
    lines.append(f"Tweets analysés : {len(tweets)}")
    lines.append("")

    lines.append("TOP NARRATIVES")
    lines.append("-" * 60)

    if narrative_counter:
        for narrative, count in narrative_counter.most_common(10):
            lines.append(f"- {narrative}: {count} mentions")
    else:
        lines.append("Aucune narrative forte détectée.")

    lines.append("")
    lines.append("TOP TICKERS")
    lines.append("-" * 60)

    if ticker_mentions:
        ranked = []

        for ticker, mentions in ticker_mentions.items():
            ranked.append((ticker, score_ticker(ticker, mentions), mentions))

        ranked.sort(key=lambda x: x[1], reverse=True)

        for ticker, score, mentions in ranked[:20]:
            authors = sorted({m["author"] for m in mentions})
            lines.append(
                f"{ticker} — Score {score}/100 — "
                f"{len(mentions)} mentions — Comptes: {', '.join('@' + a for a in authors)}"
            )

            for m in mentions[:3]:
                lines.append(f"  • @{m['author']}: {m['text']}")
                if m["url"]:
                    lines.append(f"    {m['url']}")

            lines.append("")
    else:
        lines.append("Aucun cashtag détecté.")

    lines.append("")
    lines.append("CONTRATS / LIENS DEX / PUMPFUN DETECTES")
    lines.append("-" * 60)

    if new_contracts:
        for item in new_contracts[:15]:
            lines.append(f"@{item['author']}: {item['text']}")

            if item["contracts"]:
                lines.append(f"  Contrats: {', '.join(item['contracts'])}")

            if item["dex_links"]:
                lines.append(f"  DexScreener: {', '.join(item['dex_links'])}")

            if item["pump_links"]:
                lines.append(f"  Pump.fun: {', '.join(item['pump_links'])}")

            if item["gecko_links"]:
                lines.append(f"  GeckoTerminal: {', '.join(item['gecko_links'])}")

            if item["url"]:
                lines.append(f"  Tweet: {item['url']}")

            lines.append("")
    else:
        lines.append("Aucun contrat ou lien DEX/Pump.fun détecté.")

    lines.append("")
    lines.append("RESUME")
    lines.append("-" * 60)

    if ticker_mentions:
        lines.append("Des tickers ont été détectés. Les plus intéressants sont ceux mentionnés par plusieurs comptes indépendants.")
    else:
        lines.append("Aucun ticker crypto détecté dans cette fenêtre.")

    if narrative_counter:
        top_narrative = narrative_counter.most_common(1)[0][0]
        lines.append(f"Narrative dominante actuelle : {top_narrative}.")
    else:
        lines.append("Aucune narrative dominante claire.")

    return "\n".join(lines)


def send_email(subject, body):
    if not all([EMAIL_FROM, EMAIL_TO, EMAIL_PASSWORD, SMTP_SERVER, SMTP_PORT]):
        raise ValueError("Secrets email manquants")

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


def main():
    if not TWITTERAPI_KEY:
        raise ValueError("TWITTERAPI_KEY manquant dans les secrets GitHub")

    accounts = load_accounts()
    print(f"Comptes chargés : {len(accounts)}")

    all_tweets = []

    for account in accounts:
        tweets = fetch_latest_tweets(account, limit=20)
        print(f"@{account}: {len(tweets)} tweets récupérés")
        all_tweets.extend(tweets)

    report = build_report(all_tweets)

    print("\n" + "=" * 80)
    print(report)
    print("=" * 80)

    send_email("Crypto X Trend Report", report)
    print("Email envoyé.")


if __name__ == "__main__":
    main()
