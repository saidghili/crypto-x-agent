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

print("VERSION V8 - CRYPTO X AGENT - NARRATIVES + BLACKLIST + CATEGORIES STRICTES")

TWITTERAPI_KEY = os.getenv("TWITTERAPI_KEY")

EMAIL_FROM = os.getenv("EMAIL_FROM")
EMAIL_TO = os.getenv("EMAIL_TO")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")
SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.laposte.net")
SMTP_PORT = int(os.getenv("SMTP_PORT", "465"))

OUTPUT_DIR = os.getenv("OUTPUT_DIR", "reports")
MAX_TWEETS_PER_ACCOUNT = int(os.getenv("MAX_TWEETS_PER_ACCOUNT", "20"))
SEND_EMAIL_REPORT = os.getenv("SEND_EMAIL_REPORT", "true").lower() == "true"

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
    """Détecte les tweets promotionnels/annonces"""
    promo_patterns = [
        r'committing\s+\$',
        r'launching\s+',
        r'celebrate',
        r'excited\s+to\s+announce',
        r'proud\s+to\s+present',
        r'we\s+(?:are\s+)?committed',
        r'100k|1m\s+(?:in|incentive)',
        r'weekly\s+(?:pot|bounty)',
    ]
    text_lower = (text or "").lower()
    return any(re.search(pattern, text_lower) for pattern in promo_patterns)


def analyze_sentiment(text):
    """Analyse sentiment avec contexte pour tweets promotionnels"""
    text_lower = (text or "").lower()
    positive_count = sum(1 for word in POSITIVE_KEYWORDS if word in text_lower)
    negative_count = sum(1 for word in NEGATIVE_KEYWORDS if word in text_lower)

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
    """Détecte les narratives avec word boundaries pour éviter le bruit"""
    text_l = (text or "").lower()
    narratives = []
    for name, keywords in NARRATIVE_KEYWORDS.items():
        for keyword in keywords:
            if re.search(rf'\b{re.escape(keyword)}\b', text_l):
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
        if m["sentiment"] < -0.4:
            risk_penalty += 20

    if ticker in KNOWN_LARGE_CAPS and author_count == 1:
        risk_penalty += 30

    sentiment_factor = max(-0.5, min(1.0, avg_sentiment))
    raw = consensus_score + mention_score + min(tier_score / 2, 30) + min(contract_bonus, 25) + min(engagement_bonus, 15)
    raw = raw * (1 + max(0, sentiment_factor) * 0.35) - risk_penalty

    if author_count == 1:
        tier_1_author = any(get_author_tier(a) == 1 for a in authors)
        has_contract = any(m["has_contract_or_link"] for m in mentions)
        if tier_1_author and has_contract:
            raw = min(raw, 65)
        else:
            raw = min(raw, 45)

    return round(max(0, min(raw, 100)), 2)


def classify_signal(ticker, mentions, score, avg_sentiment):
    """Classifie un ticker dans une catégorie de signal"""
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
        signal_type = classify_signal(ticker, mentions, score, avg_sentiment)
        ranked.append({
            "ticker": ticker,
            "score": score,
            "avg_sentiment": round(avg_sentiment, 3),
            "mention_count": len(mentions),
            "author_count": len(authors),
            "authors": authors,
            "signal_type": signal_type,
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
    lines.append("Crypto X Trend Report V8 - Narratives + Blacklist Strict + Categories")
    lines.append("=" * 80)
    lines.append(f"Date UTC : {data['generated_at_utc']}")
    lines.append(f"Tweets analysés après déduplication : {data['tweets_analyzed']}")
    lines.append(f"Tweets ignorés car listes de tickers : {data['ignored_list_tweets']}")
    lines.append("")

    lines.append("TOP NARRATIVES (word boundaries, pas de bruit)")
    lines.append("-" * 80)
    if data["narratives"]:
        for narrative, count in data["narratives"]:
            lines.append(f"  {narrative}: {count} mentions")
    else:
        lines.append("  Aucune narrative forte détectée.")
    lines.append("")

    lines.append("SIGNAUX D'ACHAT FORTS (Score 70+, Sentiment > 0.3, 2+ comptes ou Tier1 + contrat)")
    lines.append("-" * 80)
    if data["strong_buy"]:
        for r in data["strong_buy"][:10]:
            lines.append(
                f"  {r['ticker']} — Score {r['score']}/100 — Sentiment {r['avg_sentiment']} — "
                f"{r['mention_count']} mentions — {r['author_count']} comptes: "
                f"{', '.join('@' + a for a in r['authors'])}"
            )
            for m in r["mentions"][:2]:
                lines.append(f"    @{m['author']}: {m['text']}")
                lines.append(f"    {m['url']}")
            lines.append("")
    else:
        lines.append("  Aucun signal d'achat fort détecté.")
    lines.append("")

    lines.append("WATCHLIST PRIORITAIRE (Score 60+, Sentiment > 0.1, 2+ comptes ou Tier1)")
    lines.append("-" * 80)
    if data["watchlist"]:
        for r in data["watchlist"][:15]:
            lines.append(
                f"  {r['ticker']} — Score {r['score']}/100 — Sentiment {r['avg_sentiment']} — "
                f"{r['mention_count']} mentions — {r['author_count']} comptes: "
                f"{', '.join('@' + a for a in r['authors'])}"
            )
            lines.append(f"    Statut: À surveiller, vérifier techniquement avant entrée")
        lines.append("")
    else:
        lines.append("  Aucun ticker en watchlist.")
    lines.append("")

    lines.append("RED FLAGS & ALERTES SÉVÈRES (Vraiment négatif)")
    lines.append("-" * 80)
    if data["red_flags"]:
        for r in data["red_flags"][:10]:
            lines.append(
                f"  {r['ticker']} — Score {r['score']}/100 — Sentiment {r['avg_sentiment']} — "
                f"Raison: Mots négatifs détectés (scam, hack, rug, honeypot, etc)"
            )
            for m in r["mentions"][:1]:
                lines.append(f"    @{m['author']}: {m['text']}")
            lines.append("")
    else:
        lines.append("  Aucune alerte sévère détectée.")
    lines.append("")

    lines.append("CONTRATS DÉTECTÉS / LIENS DEX / PUMP.FUN")
    lines.append("-" * 80)
    if data["new_contracts"]:
        for item in data["new_contracts"][:10]:
            sentiment_indicator = "POSITIF" if item["sentiment"] > 0 else "NEGATIF" if item["sentiment"] < 0 else "NEUTRE"
            lines.append(f"  @{item['author']} [{sentiment_indicator}]: {item['text']}")
            if item["contracts"]:
                lines.append(f"    EVM: {', '.join(item['contracts'][:2])}")
            if item["sol_contracts"]:
                lines.append(f"    Solana: {', '.join(item['sol_contracts'][:2])}")
            lines.append(f"    {item['url']}")
            lines.append("")
    else:
        lines.append("  Aucun contrat ou lien DEX détecté.")
    lines.append("")

    lines.append("NOTES TECHNIQUES V8")
    lines.append("-" * 80)
    lines.append("  Narratives détectées avec word boundaries (\\b) pour éliminer le bruit")
    lines.append("  Blacklist enrichie: indices boursiers, actions, ETF, lettres seules")
    lines.append("  Sentiment: plus nuancé pour tweets promotionnels, moins de faux positifs")
    lines.append("  Catégories: Strong buy (70+, strict), Watchlist (60+, à vérifier), Red flags (vrais signaux négatifs)")
    lines.append("  Score plafonné à 45 pour single-account sauf Tier1 + contrat (plafonné 65)")
    lines.append("  Ce rapport n'est pas un conseil: détecte les signaux sociaux uniquement.")
    return "\n".join(lines)


def save_outputs(data, report):
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M")
    txt_path = os.path.join(OUTPUT_DIR, f"crypto_x_report_v8_{stamp}.txt")
    json_path = os.path.join(OUTPUT_DIR, f"crypto_x_report_v8_{stamp}.json")
    csv_path = os.path.join(OUTPUT_DIR, f"crypto_x_ranked_v8_{stamp}.csv")

    with open(txt_path, "w", encoding="utf-8") as f:
        f.write(report)

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    with open(csv_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["ticker", "score", "sentiment", "mentions", "author_count", "signal_type", "authors"])
        for r in data["ranked"]:
            writer.writerow([
                r["ticker"], r["score"], r["avg_sentiment"], r["mention_count"],
                r["author_count"], r["signal_type"], ", ".join(r["authors"])
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
    print(f"Rapports sauvegardés:")
    print(f"  TXT: {txt_path}")
    print(f"  JSON: {json_path}")
    print(f"  CSV: {csv_path}")

    if SEND_EMAIL_REPORT:
        send_email("Crypto X Trend Report V8", report)
        print("Email envoyé.")
    else:
        print("Envoi email désactivé: SEND_EMAIL_REPORT=false")


if __name__ == "__main__":
    main()
