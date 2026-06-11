import os
import re
import smtplib
import requests
from datetime import datetime, timezone
from collections import defaultdict, Counter
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart


print("VERSION V5 - CRYPTO X AGENT - TIERED SORSA WEIGHTING - 2026-06-11")

TWITTERAPI_KEY = os.getenv("TWITTERAPI_KEY")

EMAIL_FROM = os.getenv("EMAIL_FROM")
EMAIL_TO = os.getenv("EMAIL_TO")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")
SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.laposte.net")
SMTP_PORT = int(os.getenv("SMTP_PORT", "465"))


TIER_1 = {
    "cobie", "zachxbt", "CryptoHayes", "jessepollak",
    "blknoiz06", "HsakaTrades", "CL207", "Pentosh1"
}

TIER_2 = {
    "DegenSpartan", "nansen_ai", "0xngmi", "lookonchain",
    "MilesDeutscher", "SolBigBrain", "weremeow", "Virtuals_io",
    "DefiLlama", "DefiIgnas", "TheFlowHorse", "Route2FI", "theunipcs"
}

TIER_3 = {
    "CryptoMichNL", "CrashiusClay69", "BigCheds",
    "AltcoinSherpa", "Austin_Federa", "ByzGeneral"
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


def get_author_tier(author):
    if author in TIER_1:
        return 1
    elif author in TIER_2:
        return 2
    elif author in TIER_3:
        return 3
    else:
        return 0


def get_tier_multiplier(tier):
    if tier == 1:
        return 3.0
    elif tier == 2:
        return 2.0
    elif tier == 3:
        return 1.0
    else:
        return 0.0


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


def deduplicate_tweets(tweets):
    seen_ids = set()
    seen_texts = set()
    result = []

    for tweet in tweets:
        tweet_id = tweet.get("id")
        text_key = tweet.get("text", "").strip()[:300]

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
    raw = re.findall(r"\$[A-Za-z0-9_]{2,15}", text)
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

    return clean


def is_ticker_list_tweet(text):
    tickers = extract_tickers(text)
    return len(tickers) >= 8


def extract_contracts_and_links(text):
    evm_contracts = re.findall(r"0x[a-fA-F0-9]{40}", text)
    solana_contracts = re.findall(r"\b[1-9A-HJ-NP-Za-km-z]{32,44}\b", text)

    dexscreener_links = re.findall(r"https?://(?:www\.)?dexscreener\.com/\S+", text)
    pumpfun_links = re.findall(r"https?://(?:www\.)?pump\.fun/\S+", text)
    geckoterminal_links = re.findall(r"https?://(?:www\.)?geckoterminal\.com/\S+", text)

    return evm_contracts, solana_contracts, dexscreener_links, pumpfun_links, geckoterminal_links


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
    if views and views > 500000:
        score += 30

    return score


def score_ticker(ticker, mentions):
    score = 0
    authors = {m["author"] for m in mentions}
    author_count = len(authors)
    mention_count = len(mentions)

    if author_count == 1:
        score += 15
    elif author_count == 2:
        score += 40
    elif author_count >= 3:
        score += 65

    score += min(mention_count * 4, 20)

    if ticker in KNOWN_LARGE_CAPS and author_count == 1:
        score -= 25

    tier_weighted_points = 0

    for m in mentions:
        author = m["author"]
        author_tier = get_author_tier(author)
        tier_multiplier = get_tier_multiplier(author_tier)

        base_author_score = 0

        if author_tier == 1:
            base_author_score += 15
        elif author_tier == 2:
            base_author_score += 10
        elif author_tier == 3:
            base_author_score += 5

        if m["contracts"] or m["sol_contracts"] or m["dex_links"] or m["pump_links"] or m["gecko_links"]:
            base_author_score += 20

        if m["engagement"] > 50:
            base_author_score += 5

        if m["engagement"] > 250:
            base_author_score += 10

        tier_weighted_points += base_author_score * tier_multiplier

    score += min(tier_weighted_points / 2, 35)

    if author_count == 1:
        score = min(score, 55)

    return max(0, min(score, 100))


def classify_ticker(ticker, mentions):
    authors = {m["author"] for m in mentions}
    has_contract = any(
        m["contracts"] or m["sol_contracts"] or m["dex_links"] or m["pump_links"] or m["gecko_links"]
        for m in mentions
    )

    if ticker in KNOWN_LARGE_CAPS:
        return "Large cap / coin connu"

    if has_contract:
        return "Possible nouveau gem / contrat détecté"

    if len(authors) >= 2:
        return "Ticker à surveiller"

    return "Signal faible"


def is_new_gem_candidate(ticker, mentions, score):
    if ticker in KNOWN_LARGE_CAPS:
        return False

    if ticker in BLACKLIST_TICKERS:
        return False

    authors = {m["author"] for m in mentions}

    has_contract = any(
        m["contracts"] or m["sol_contracts"] or m["dex_links"] or m["pump_links"] or m["gecko_links"]
        for m in mentions
    )

    if score >= 60 and len(authors) >= 2:
        return True

    if has_contract and score >= 45:
        return True

    return False


def build_report(tweets):
    tweets = deduplicate_tweets(tweets)

    ticker_mentions = defaultdict(list)
    narrative_counter = Counter()
    new_contracts = []
    ignored_list_tweets = 0

    for tweet in tweets:
        text = tweet["text"]

        narratives = detect_narratives(text)
        contracts, sol_contracts, dex_links, pump_links, gecko_links = extract_contracts_and_links(text)
        engagement = engagement_score(tweet)
        is_list = is_ticker_list_tweet(text)

        for n in narratives:
            narrative_counter[n] += 1

        if contracts or sol_contracts or dex_links or pump_links or gecko_links:
            new_contracts.append({
                "author": tweet["author"],
                "contracts": contracts,
                "sol_contracts": sol_contracts,
                "dex_links": dex_links,
                "pump_links": pump_links,
                "gecko_links": gecko_links,
                "text": text[:260],
                "url": tweet["url"]
            })

        if is_list:
            ignored_list_tweets += 1
            continue

        tickers = extract_tickers(text)

        for ticker in tickers:
            ticker_mentions[ticker].append({
                "author": tweet["author"],
                "text": text[:260],
                "url": tweet["url"],
                "contracts": contracts,
                "sol_contracts": sol_contracts,
                "dex_links": dex_links,
                "pump_links": pump_links,
                "gecko_links": gecko_links,
                "engagement": engagement,
            })

    ranked = []
    for ticker, mentions in ticker_mentions.items():
        ranked.append((ticker, score_ticker(ticker, mentions), mentions))

    ranked.sort(key=lambda x: x[1], reverse=True)

    new_gems = [
        (ticker, score, mentions)
        for ticker, score, mentions in ranked
        if is_new_gem_candidate(ticker, mentions, score)
    ]

    lines = []
    lines.append("Crypto X Trend Report V5 - TIERED SORSA WEIGHTING")
    lines.append("=" * 70)
    lines.append(f"Date UTC : {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')}")
    lines.append(f"Tweets analysés après déduplication : {len(tweets)}")
    lines.append(f"Tweets ignorés car listes de tickers : {ignored_list_tweets}")
    lines.append(f"Comptes actifs : Tier 1 (8) + Tier 2 (13) + Tier 3 (6) = 27 total")
    lines.append("")

    lines.append("TOP NARRATIVES")
    lines.append("-" * 70)

    if narrative_counter:
        for narrative, count in narrative_counter.most_common(10):
            lines.append(f"- {narrative}: {count} mentions")
    else:
        lines.append("Aucune narrative forte détectée.")

    lines.append("")
    lines.append("TOP NEW GEMS")
    lines.append("-" * 70)

    if new_gems:
        for ticker, score, mentions in new_gems[:10]:
            authors = sorted({m["author"] for m in mentions})
            classification = classify_ticker(ticker, mentions)

            lines.append(
                f"{ticker} — Score {score}/100 — {classification} — "
                f"{len(mentions)} mentions — {len(authors)} comptes: "
                f"{', '.join('@' + a for a in authors)}"
            )

            for m in mentions[:3]:
                lines.append(f"  • @{m['author']}: {m['text']}")
                if m["url"]:
                    lines.append(f"    {m['url']}")

            lines.append("")
    else:
        lines.append("Aucun nouveau gem fort détecté dans cette fenêtre.")

    lines.append("")
    lines.append("TOP SIGNAUX TICKERS")
    lines.append("-" * 70)

    if ranked:
        for ticker, score, mentions in ranked[:20]:
            authors = sorted({m["author"] for m in mentions})
            classification = classify_ticker(ticker, mentions)

            lines.append(
                f"{ticker} — Score {score}/100 — {classification} — "
                f"{len(mentions)} mentions — {len(authors)} comptes: "
                f"{', '.join('@' + a for a in authors)}"
            )

            for m in mentions[:3]:
                lines.append(f"  • @{m['author']}: {m['text']}")
                if m["url"]:
                    lines.append(f"    {m['url']}")

            lines.append("")
    else:
        lines.append("Aucun cashtag crypto détecté.")

    lines.append("")
    lines.append("NOUVEAUX CONTRATS / LIENS DEX / PUMPFUN")
    lines.append("-" * 70)

    if new_contracts:
        for item in new_contracts[:15]:
            lines.append(f"@{item['author']}: {item['text']}")

            if item["contracts"]:
                lines.append(f"  Contrats EVM: {', '.join(item['contracts'])}")

            if item["sol_contracts"]:
                lines.append(f"  Contrats Solana possibles: {', '.join(item['sol_contracts'][:3])}")

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
    lines.append("RESUME ACTIONNABLE")
    lines.append("-" * 70)

    strong = []
    watch = []

    for ticker, score, mentions in ranked:
        c = classify_ticker(ticker, mentions)

        if score >= 70:
            strong.append((ticker, score, c))
        elif score >= 40:
            watch.append((ticker, score, c))

    if strong:
        lines.append("Signaux forts :")
        for ticker, s, c in sorted(strong, key=lambda x: x[1], reverse=True):
            lines.append(f"- {ticker}: {s}/100 — {c}")
    else:
        lines.append("Aucun signal ticker vraiment fort.")

    if watch:
        lines.append("")
        lines.append("À surveiller :")
        for ticker, s, c in sorted(watch, key=lambda x: x[1], reverse=True)[:10]:
            lines.append(f"- {ticker}: {s}/100 — {c}")

    if narrative_counter:
        top_narrative = narrative_counter.most_common(1)[0][0]
        lines.append("")
        lines.append(f"Narrative dominante actuelle : {top_narrative}.")
    else:
        lines.append("")
        lines.append("Aucune narrative dominante claire.")

    lines.append("")
    lines.append("NOTES TECHNIQUES V5")
    lines.append("-" * 70)
    lines.append("Tier 1 (8 comptes, 3x multiplier): cobie, zachxbt, CryptoHayes, jessepollak, blknoiz06, HsakaTrades, CL207, Pentosh1")
    lines.append("Tier 2 (13 comptes, 2x multiplier): DegenSpartan, nansen_ai, 0xngmi, lookonchain, MilesDeutscher, SolBigBrain, weremeow, Virtuals_io, DefiLlama, DefiIgnas, TheFlowHorse, Route2FI, theunipcs")
    lines.append("Tier 3 (6 comptes, 1x multiplier): CryptoMichNL, CrashiusClay69, BigCheds, AltcoinSherpa, Austin_Federa, ByzGeneral")
    lines.append("Un score élevé n'est pas un signal d'achat automatique.")
    lines.append("Vérifier prix, volume, liquidité, contrat et risque de rug avant toute décision.")

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

    send_email("Crypto X Trend Report V5 - Tiered Sorsa Weighting", report)
    print("Email envoyé.")


if __name__ == "__main__":
    main()
