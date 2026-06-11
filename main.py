import os
import re
import csv
import json
import smtplib
import requests
from datetime import datetime, timezone
from collections import defaultdict, Counter
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

print("VERSION V7 - CRYPTO X AGENT - TREND + SENTIMENT + EXPORTS")

TWITTERAPI_KEY = os.getenv("TWITTERAPI_KEY")

EMAIL_FROM = os.getenv("EMAIL_FROM")
EMAIL_TO = os.getenv("EMAIL_TO")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")
SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.laposte.net")
SMTP_PORT = int(os.getenv("SMTP_PORT", "465"))

OUTPUT_DIR = os.getenv("OUTPUT_DIR", "reports")
MAX_TWEETS_PER_ACCOUNT = int(os.getenv("MAX_TWEETS_PER_ACCOUNT", "20"))
SEND_EMAIL_REPORT = os.getenv("SEND_EMAIL_REPORT", "true").lower() == "true"

# Comptes suivis, normalisés en minuscules pour éviter les erreurs de casse.
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
    "AltcoinSherpa", "Austin_Federa", "ByzGeneral"
}}

ANTI_SCAM_ACCOUNTS = {"zachxbt"}

POSITIVE_KEYWORDS = {
    "bullish", "accumulate", "loading", "buy", "buying", "strong", "upside",
    "breakout", "support", "holding", "long", "pump", "moon", "gem", "alpha",
    "early", "opportunity", "entry", "dip", "accumulation", "going higher",
    "outperform", "undervalued", "setup", "catalysts", "loaded", "cheap",
    "reversal", "confirmation", "strength", "bullish momentum", "oversold", "bounce",
    "recovery", "rally", "gaining", "momentum", "positive"
}

NEGATIVE_KEYWORDS = {
    "bearish", "sold", "selling", "exit", "exited", "rug", "scam",
    "fraud", "suspicious", "crash", "trap", "avoid", "danger",
    "wrong direction", "out", "red flag", "warning", "beware", "caution",
    "manipulation", "exploit", "hack", "exposed", "negative", "concern",
    "liquidated", "rekt", "collapse", "failed", "dead", "untrustworthy",
    "malicious", "attack", "vulnerable", "breach"
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
    "AI / AI Agents": ["ai", "agent", "agents", "virtuals", "deai", "autonomous"],
    "Memecoin": ["meme", "memecoin", "memecoins", "pump", "degen", "degens"],
    "Solana": ["solana", "sol", "pumpfun", "pump.fun", "jupiter", "bonk"],
    "Base": ["base", "brett", "toshi", "buildonbase"],
    "RWA": ["rwa", "tokenization", "tokenized", "treasury", "ondo"],
    "DePIN": ["depin"],
    "DeFi": ["defi", "yield", "perps", "dex", "liquidity", "lending"],
    "Restaking": ["restaking", "eigen", "eigenlayer"],
    "Gaming": ["gaming", "gamefi", "play-to-earn", "p2e"],
}

BLACKLIST_TICKERS = {
    "$USD", "$USDT", "$USDC", "$BTC", "$ETH",
    "$SPY", "$QQQ", "$DIA", "$IWM", "$VIX",
    "$XAU", "$XAG", "$GOLD", "$SILVER", "$OIL",
    "$ORCL", "$SMCI", "$CPB", "$TSLA", "$AAPL",
    "$MSFT", "$GOOGL", "$GOOG", "$AMZN", "$META",
    "$NVDA", "$NFLX", "$AMD", "$INTC", "$PLTR",
    "$MSTR", "$COIN", "$HOOD", "$NKE", "$DIS",
    "$K", "$M", "$B"
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


def analyze_sentiment(text):
    text_lower = (text or "").lower()
    positive_count = sum(1 for word in POSITIVE_KEYWORDS if word in text_lower)
    negative_count = sum(1 for word in NEGATIVE_KEYWORDS if word in text_lower)

    for pattern in BULLISH_PATTERNS:
        if pattern in text_lower:
            positive_count += 2
    for pattern in BEARISH_PATTERNS:
        if pattern in text_lower:
            negative_count += 2

    if positive_count + negative_count == 0:
        return 0.0

    sentiment = (positive_count - negative_count) / (positive_count + negative_count)
    return max(-1.0, min(1.0, sentiment))


def load_accounts(path="accounts.txt"):
    with open(path, "r", encoding="utf-8") as f:
        accounts = []
        for line in f:
            account = norm_author(line)
            if account:
                accounts.append(account)
    return list(dict.fromkeys(accounts))


def fetch_latest_tweets(username, limit=20):
    url = "https://api.twitterapi.io/twitter/user/last_tweets"
    headers = {"X-API-Key": TWITTERAPI_KEY}
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

    tweets = data.get("data", {}).get("tweets", []) if isinstance(data, dict) else []
    if not isinstance(tweets, list):
        print(f"FORMAT INATTENDU @{username}: {str(data)[:500]}")
        return []

    cleaned = []
    for t in tweets:
        if not isinstance(t, dict):
            continue

        text = t.get("text") or ""
        tweet_id = t.get("id") or ""
        if not text:
            continue

        # Filtre simple retweet natif / texte commençant par RT.
        if text.strip().lower().startswith("rt @"):
            continue

        cleaned.append({
            "id": tweet_id,
            "author": norm_author(username),
            "text": text,
            "created_at": t.get("createdAt") or "",
            "url": t.get("url") or f"https://x.com/{username}/status/{tweet_id}",
            "like_count": t.get("likeCount", 0) or 0,
            "retweet_count": t.get("retweetCount", 0) or 0,
            "reply_count": t.get("replyCount", 0) or 0,
            "view_count": t.get("viewCount", 0) or 0,
        })
    return cleaned


def deduplicate_tweets(tweets):
    seen_ids = set()
    seen_texts = set()
    result = []
    for tweet in tweets:
        tweet_id = tweet.get("id")
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
    return [name for name, keywords in NARRATIVE_KEYWORDS.items() if any(k in text_l for k in keywords)]


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


def score_ticker(ticker, mentions):
    authors = {m["author"] for m in mentions}
    author_count = len(authors)
    mention_count = len(mentions)
    avg_sentiment = sum(m["sentiment"] for m in mentions) / len(mentions)

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
        if m["sentiment"] < -0.2:
            risk_penalty += 15

    if ticker in KNOWN_LARGE_CAPS and author_count == 1:
        risk_penalty += 25

    sentiment_factor = max(-0.5, min(1.0, avg_sentiment))
    raw = consensus_score + mention_score + min(tier_score / 2, 30) + min(contract_bonus, 25) + min(engagement_bonus, 15)
    raw = raw * (1 + max(0, sentiment_factor) * 0.35) - risk_penalty

    if author_count == 1:
        raw = min(raw, 55)

    return round(max(0, min(raw, 100)), 2)


def classify_ticker(ticker, mentions):
    authors = {m["author"] for m in mentions}
    has_contract = any(m["has_contract_or_link"] for m in mentions)
    avg_sentiment = sum(m["sentiment"] for m in mentions) / len(mentions)

    if avg_sentiment < -0.35:
        return "Risque / sentiment négatif"
    if ticker in KNOWN_LARGE_CAPS:
        return "Large cap / coin connu"
    if has_contract:
        return "Possible nouveau gem / contrat détecté"
    if len(authors) >= 2:
        return "Ticker à surveiller"
    return "Signal faible"


def build_report_data(tweets):
    tweets = deduplicate_tweets(tweets)
    ticker_mentions = defaultdict(list)
    narrative_counter = Counter()
    new_contracts = []
    ignored_list_tweets = 0

    for tweet in tweets:
        text = tweet["text"]
        sentiment = analyze_sentiment(text)
        engagement = engagement_score(tweet)
        narratives = detect_narratives(text)
        contracts, sol_contracts, dex_links, pump_links, gecko_links = extract_contracts_and_links(text)
        has_contract_or_link = bool(contracts or sol_contracts or dex_links or pump_links or gecko_links)

        for n in narratives:
            narrative_counter[n] += 1

        if has_contract_or_link:
            new_contracts.append({
                "author": tweet["author"],
                "contracts": contracts,
                "sol_contracts": sol_contracts,
                "dex_links": dex_links,
                "pump_links": pump_links,
                "gecko_links": gecko_links,
                "text": text[:260],
                "url": tweet["url"],
                "sentiment": sentiment,
            })

        if is_ticker_list_tweet(text):
            ignored_list_tweets += 1
            continue

        for ticker in extract_tickers(text):
            ticker_mentions[ticker].append({
                "author": tweet["author"],
                "text": text[:260],
                "url": tweet["url"],
                "engagement": engagement,
                "sentiment": sentiment,
                "has_contract_or_link": has_contract_or_link,
            })

    ranked = []
    for ticker, mentions in ticker_mentions.items():
        score = score_ticker(ticker, mentions)
        avg_sentiment = sum(m["sentiment"] for m in mentions) / len(mentions)
        authors = sorted({m["author"] for m in mentions})
        ranked.append({
            "ticker": ticker,
            "score": score,
            "avg_sentiment": round(avg_sentiment, 3),
            "mention_count": len(mentions),
            "author_count": len(authors),
            "authors": authors,
            "classification": classify_ticker(ticker, mentions),
            "mentions": mentions,
        })

    ranked.sort(key=lambda x: x["score"], reverse=True)

    buy_signals = [
        r for r in ranked
        if r["score"] >= 60 and r["avg_sentiment"] > 0.15 and r["classification"] != "Large cap / coin connu"
    ]

    red_flags = [
        r for r in ranked
        if r["avg_sentiment"] < -0.35 or any(
            m["author"] in ANTI_SCAM_ACCOUNTS and m["sentiment"] < -0.2 for m in r["mentions"]
        )
    ]

    return {
        "generated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M"),
        "tweets_analyzed": len(tweets),
        "ignored_list_tweets": ignored_list_tweets,
        "narratives": narrative_counter.most_common(10),
        "ranked": ranked,
        "buy_signals": buy_signals,
        "red_flags": red_flags,
        "new_contracts": new_contracts,
    }


def build_text_report(data):
    lines = []
    lines.append("Crypto X Trend Report V7 - Trend + Sentiment + Exports")
    lines.append("=" * 72)
    lines.append(f"Date UTC : {data['generated_at_utc']}")
    lines.append(f"Tweets analysés après déduplication : {data['tweets_analyzed']}")
    lines.append(f"Tweets ignorés car listes de tickers : {data['ignored_list_tweets']}")
    lines.append("")

    lines.append("TOP NARRATIVES")
    lines.append("-" * 72)
    if data["narratives"]:
        for narrative, count in data["narratives"]:
            lines.append(f"- {narrative}: {count} mentions")
    else:
        lines.append("Aucune narrative forte détectée.")

    lines.append("\nSIGNAUX D'ACHAT FORTS")
    lines.append("-" * 72)
    if data["buy_signals"]:
        for r in data["buy_signals"][:10]:
            lines.append(
                f"{r['ticker']} — Score {r['score']}/100 — Sentiment {r['avg_sentiment']} — "
                f"{r['classification']} — {r['mention_count']} mentions — {r['author_count']} comptes: "
                f"{', '.join('@' + a for a in r['authors'])}"
            )
            for m in r["mentions"][:3]:
                lines.append(f"  • @{m['author']}: {m['text']}")
                lines.append(f"    {m['url']}")
            lines.append("")
    else:
        lines.append("Aucun signal d'achat fort détecté dans cette fenêtre.")

    lines.append("\nRED FLAGS & ALERTES DE RISQUE")
    lines.append("-" * 72)
    if data["red_flags"]:
        for r in data["red_flags"][:10]:
            lines.append(
                f"{r['ticker']} — Score {r['score']}/100 — Sentiment {r['avg_sentiment']} — "
                f"{r['classification']} — {r['mention_count']} mentions"
            )
            for m in r["mentions"][:2]:
                lines.append(f"  • @{m['author']}: {m['text']}")
                lines.append(f"    {m['url']}")
            lines.append("")
    else:
        lines.append("Aucune alerte de risque détectée.")

    lines.append("\nTOP SIGNAUX TICKERS")
    lines.append("-" * 72)
    if data["ranked"]:
        for r in data["ranked"][:15]:
            label = "+" if r["avg_sentiment"] > 0.2 else "-" if r["avg_sentiment"] < -0.2 else "Neutre"
            lines.append(
                f"{r['ticker']} — Score {r['score']}/100 — {label} — {r['classification']} — "
                f"{r['mention_count']} mentions — {r['author_count']} comptes"
            )
    else:
        lines.append("Aucun cashtag crypto détecté.")

    lines.append("\nNOUVEAUX CONTRATS / LIENS DEX / PUMPFUN")
    lines.append("-" * 72)
    if data["new_contracts"]:
        for item in data["new_contracts"][:10]:
            sentiment_indicator = "POSITIF" if item["sentiment"] > 0 else "NEGATIF" if item["sentiment"] < 0 else "NEUTRE"
            lines.append(f"@{item['author']} [{sentiment_indicator}]: {item['text']}")
            if item["contracts"]:
                lines.append(f"  Contrats EVM: {', '.join(item['contracts'][:2])}")
            if item["sol_contracts"]:
                lines.append(f"  Contrats Solana possibles: {', '.join(item['sol_contracts'][:2])}")
            lines.append(f"  {item['url']}\n")
    else:
        lines.append("Aucun contrat ou lien DEX/Pump.fun détecté.")

    lines.append("\nNOTES TECHNIQUES V7")
    lines.append("-" * 72)
    lines.append("- Comptes normalisés en minuscules pour éviter les erreurs de casse.")
    lines.append("- Export automatique TXT, JSON et CSV pour suivi historique/backtest.")
    lines.append("- Score basé sur consensus, tier, sentiment, engagement et présence de contrat/lien DEX.")
    lines.append("- Les signaux d'achat exigent score élevé, sentiment positif et exclusion des large caps connues.")
    lines.append("- Ce rapport n'est pas un conseil financier : il détecte uniquement des signaux sociaux.")
    return "\n".join(lines)


def save_outputs(data, report):
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M")
    txt_path = os.path.join(OUTPUT_DIR, f"crypto_x_report_{stamp}.txt")
    json_path = os.path.join(OUTPUT_DIR, f"crypto_x_report_{stamp}.json")
    csv_path = os.path.join(OUTPUT_DIR, f"crypto_x_ranked_{stamp}.csv")

    with open(txt_path, "w", encoding="utf-8") as f:
        f.write(report)

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    with open(csv_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["ticker", "score", "avg_sentiment", "mention_count", "author_count", "classification", "authors"])
        for r in data["ranked"]:
            writer.writerow([
                r["ticker"], r["score"], r["avg_sentiment"], r["mention_count"],
                r["author_count"], r["classification"], ", ".join(r["authors"])
            ])

    return txt_path, json_path, csv_path


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
        raise ValueError("TWITTERAPI_KEY manquant dans les variables d'environnement")

    accounts = load_accounts()
    print(f"Comptes chargés : {len(accounts)}")

    all_tweets = []
    for account in accounts:
        tweets = fetch_latest_tweets(account, limit=MAX_TWEETS_PER_ACCOUNT)
        print(f"@{account}: {len(tweets)} tweets récupérés")
        all_tweets.extend(tweets)

    data = build_report_data(all_tweets)
    report = build_text_report(data)
    txt_path, json_path, csv_path = save_outputs(data, report)

    print("\n" + "=" * 80)
    print(report)
    print("=" * 80)
    print(f"Rapports sauvegardés : {txt_path}, {json_path}, {csv_path}")

    if SEND_EMAIL_REPORT:
        send_email("Crypto X Trend Report V7", report)
        print("Email envoyé.")
    else:
        print("Envoi email désactivé: SEND_EMAIL_REPORT=false")


if __name__ == "__main__":
    main()
