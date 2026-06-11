import os
import re
import requests
from datetime import datetime, timezone
from collections import defaultdict, Counter


print("VERSION TEST TWITTERAPI.IO SANS EMAIL 2026-06-11")

TWITTERAPI_KEY = os.getenv("TWITTERAPI_KEY")


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
    # Endpoint à tester : Get User Last Tweets
    # Si celui-ci ne marche pas, on ajustera avec l'URL exacte de TwitterAPI.io.
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
        print(f"ERREUR REQUETE {username}: {e}")
        return []

    print(f"\nSTATUS {username}: {r.status_code}")
    print(f"URL appelée: {r.url}")
    print(f"REPONSE BRUTE {username}:")
    print(r.text[:1200])

    if r.status_code != 200:
        return []

    try:
        data = r.json()
    except Exception as e:
        print(f"ERREUR JSON {username}: {e}")
        return []

    tweets = []

    # Formats possibles selon API
    if isinstance(data, dict):
        if "tweets" in data and isinstance(data["tweets"], list):
            tweets = data["tweets"]

        elif "data" in data and isinstance(data["data"], list):
            tweets = data["data"]

        elif "data" in data and isinstance(data["data"], dict):
            if "tweets" in data["data"] and isinstance(data["data"]["tweets"], list):
                tweets = data["data"]["tweets"]
            elif "data" in data["data"] and isinstance(data["data"]["data"], list):
                tweets = data["data"]["data"]
            elif "items" in data["data"] and isinstance(data["data"]["items"], list):
                tweets = data["data"]["items"]

        elif "result" in data and isinstance(data["result"], list):
            tweets = data["result"]

        elif "items" in data and isinstance(data["items"], list):
            tweets = data["items"]

    cleaned = []

    for t in tweets:
        if not isinstance(t, dict):
            continue

        text = (
            t.get("text")
            or t.get("content")
            or t.get("full_text")
            or t.get("tweetText")
            or ""
        )

        created_at = (
            t.get("createdAt")
            or t.get("created_at")
            or t.get("created_time")
            or t.get("created")
            or ""
        )

        tweet_id = (
            t.get("id")
            or t.get("tweetId")
            or t.get("tweet_id")
            or t.get("rest_id")
            or ""
        )

        if text:
            cleaned.append({
                "id": tweet_id,
                "author": username,
                "text": text,
                "created_at": created_at,
                "url": f"https://x.com/{username}/status/{tweet_id}" if tweet_id else ""
            })

    print(f"TWEETS NETTOYES {username}: {len(cleaned)}")

    return cleaned


def extract_tickers(text):
    tickers = re.findall(r"\$[A-Za-z]{2,10}", text)

    blacklist = {
        "$USD", "$USDT", "$USDC", "$BTC", "$ETH"
    }

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

        for ticker, score, mentions in ranked[:20]:
            authors = sorted({m["author"] for m in mentions})
            lines.append(
                f"{ticker} — Score {score}/100 — "
                f"{len(mentions)} mentions — Comptes: {', '.join(authors)}"
            )

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


def main():
    if not TWITTERAPI_KEY:
        raise ValueError("TWITTERAPI_KEY manquant dans les secrets GitHub")

    accounts = load_accounts()
    print(f"Comptes chargés : {len(accounts)}")

    all_tweets = []

    for account in accounts:
        tweets = fetch_latest_tweets(account, limit=20)
        print(f"{account}: {len(tweets)} tweets nettoyés")
        all_tweets.extend(tweets)

    report = build_report(all_tweets)

    print("\n" + "=" * 80)
    print(report)
    print("=" * 80)

    print("EMAIL DESACTIVE TEMPORAIREMENT")
    print("Objectif actuel : corriger d'abord la récupération TwitterAPI.io")


if __name__ == "__main__":
    main()
