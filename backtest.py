#!/usr/bin/env python3
import os
import json
import argparse
from datetime import datetime, timedelta
from collections import defaultdict
import requests


def load_all_reports(reports_dir):
    reports = []
    if not os.path.exists(reports_dir):
        print(f"ERROR: directory not found: {reports_dir}")
        return []
    for filename in sorted(os.listdir(reports_dir)):
        if filename.endswith(".json") and ("_v10_" in filename or "_v91_" in filename):
            path = os.path.join(reports_dir, filename)
            try:
                with open(path, "r", encoding="utf-8") as f:
                    reports.append({"filename": filename, "path": path, "data": json.load(f)})
                print(f"Loaded: {filename}")
            except Exception as e:
                print(f"ERROR loading {filename}: {e}")
    return reports


def get_price_history(ticker, lookback_hours=72):
    try:
        symbol = ticker.lstrip("$").lower()
        r = requests.get("https://api.coingecko.com/api/v3/search", params={"query": symbol}, timeout=10)
        if r.status_code != 200:
            return None
        coins = r.json().get("coins", [])
        if not coins:
            return None
        coin = next((c for c in coins if (c.get("symbol") or "").upper() == ticker.lstrip("$").upper()), coins[0])
        coin_id = coin.get("id")
        if not coin_id:
            return None
        days = max(1, lookback_hours // 24 + 1)
        r2 = requests.get(
            f"https://api.coingecko.com/api/v3/coins/{coin_id}/market_chart",
            params={"vs_currency": "usd", "days": days},
            timeout=10,
        )
        if r2.status_code != 200:
            return None
        return r2.json()
    except Exception as e:
        print(f"  price history error {ticker}: {e}")
        return None


def calculate_return(signal_price, signal_time, target_hours, price_history):
    try:
        if not price_history or "prices" not in price_history:
            return None
        if not signal_price or signal_price <= 0:
            return None
        signal_dt = datetime.fromisoformat(signal_time.replace("Z", "+00:00"))
        target_ts = int((signal_dt + timedelta(hours=target_hours)).timestamp() * 1000)
        closest_price = None
        min_diff = float("inf")
        for timestamp, price in price_history.get("prices", []):
            diff = abs(timestamp - target_ts)
            if diff < min_diff:
                min_diff = diff
                closest_price = price
        if closest_price is None:
            return None
        return ((closest_price - signal_price) / signal_price) * 100
    except Exception:
        return None


def backtest_signals(reports, lookback_hours=72):
    all_signals = []
    verdict_results = defaultdict(list)
    signal_type_results = defaultdict(list)
    account_results = defaultdict(list)

    for report in reports:
        ranked = report["data"].get("ranked", [])
        print(f"Processing {len(ranked)} signals from {report['filename']}...")
        for signal in ranked:
            ticker = signal.get("ticker")
            signal_price = signal.get("current_price_usd")
            signal_time = signal.get("signal_timestamp_utc")
            if not all([ticker, signal_price, signal_time]):
                continue
            history = get_price_history(ticker, lookback_hours)
            return_pct = calculate_return(signal_price, signal_time, lookback_hours, history)
            gpt = signal.get("gpt_analysis") or {}
            result = {
                "ticker": ticker,
                "score": signal.get("score"),
                "signal_type": signal.get("signal_type"),
                "verdict": gpt.get("verdict"),
                "recommendation": gpt.get("recommendation"),
                "return_pct": return_pct,
                "success": return_pct > 0 if return_pct is not None else None,
                "authors": signal.get("authors", []),
            }
            all_signals.append(result)
            if return_pct is not None:
                if result["verdict"]:
                    verdict_results[result["verdict"]].append(return_pct)
                if result["signal_type"]:
                    signal_type_results[result["signal_type"]].append(return_pct)
                for author in result["authors"]:
                    account_results[author].append(return_pct)

    known = [s for s in all_signals if s["return_pct"] is not None]
    winners = [s for s in known if s["return_pct"] > 0]
    losers = [s for s in known if s["return_pct"] <= 0]
    print("=" * 80)
    print(f"Analyzed signals: {len(all_signals)} | priced: {len(known)} | unknown: {len(all_signals) - len(known)}")
    print(f"Win rate: {len(winners) / max(1, len(known)) * 100:.1f}%")
    if winners:
        print(f"Average winner: {sum(s['return_pct'] for s in winners) / len(winners):+.2f}%")
    if losers:
        print(f"Average loser: {sum(s['return_pct'] for s in losers) / len(losers):+.2f}%")
    print()

    def print_group(title, groups):
        print(title)
        print("-" * 80)
        for key, returns in sorted(groups.items(), key=lambda item: len(item[1]), reverse=True):
            if not returns:
                continue
            win_rate = len([r for r in returns if r > 0]) / len(returns) * 100
            avg_return = sum(returns) / len(returns)
            print(f"  {key}: {len(returns)} signals | win {win_rate:.1f}% | avg {avg_return:+.2f}%")
        print()

    print_group("By GPT verdict", verdict_results)
    print_group("By signal type", signal_type_results)
    print_group("By account", dict(sorted(account_results.items(), key=lambda item: len(item[1]), reverse=True)[:15]))

    sorted_signals = sorted(known, key=lambda s: s["return_pct"], reverse=True)
    print("Top signals")
    print("-" * 80)
    for s in sorted_signals[:10]:
        print(f"  {s['ticker']} [{s.get('verdict') or s.get('signal_type')}]: {s['return_pct']:+.2f}% score={s.get('score')}")
    print()
    print("Worst signals")
    print("-" * 80)
    for s in sorted_signals[-10:]:
        print(f"  {s['ticker']} [{s.get('verdict') or s.get('signal_type')}]: {s['return_pct']:+.2f}% score={s.get('score')}")

    summary = {
        "total_signals": len(all_signals),
        "priced_signals": len(known),
        "win_rate": len(winners) / max(1, len(known)) * 100,
        "all_signals": all_signals,
    }
    output_path = os.path.join(args.reports, "backtest_results.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)
    print(f"Saved: {output_path}")


def parse_lookback(value):
    value = value.lower().strip()
    if value.endswith("h"):
        return int(value[:-1])
    if value.endswith("d"):
        return int(value[:-1]) * 24
    return int(value)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Crypto X Agent V10 backtest")
    parser.add_argument("--reports", default="reports", help="Directory containing JSON reports")
    parser.add_argument("--lookback", default="72h", help="Lookback period, e.g. 24h, 72h, 7d")
    args = parser.parse_args()
    loaded_reports = load_all_reports(args.reports)
    backtest_signals(loaded_reports, parse_lookback(args.lookback))
