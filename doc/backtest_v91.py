#!/usr/bin/env python3
"""
Crypto X Agent V9.1 - Backtesting Framework
===========================================

Usage:
  python backtest_v91.py --reports reports/ --lookback 72h

Analyzes historical signals (JSON reports) against price movements.
Measures accuracy, win/loss ratio, Sharpe ratio, performance by tier.

Run this AFTER collecting 15+ days of signal data.
"""

import os
import json
import sys
import argparse
from datetime import datetime, timedelta, timezone
from collections import defaultdict, Counter
import requests

try:
    import statistics
    HAS_STATS = True
except ImportError:
    HAS_STATS = False

def load_all_reports(reports_dir):
    """Charge tous les JSON reports du rÃ©pertoire"""
    reports = []
    if not os.path.exists(reports_dir):
        print(f"ERROR: Directory not found: {reports_dir}")
        return []
    
    for filename in sorted(os.listdir(reports_dir)):
        if '_v91_' in filename and filename.endswith('.json'):
            filepath = os.path.join(reports_dir, filename)
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    reports.append({
                        'filename': filename,
                        'path': filepath,
                        'data': data,
                        'timestamp': datetime.fromisoformat(data.get('generated_at_utc').replace(' ', 'T').replace('Z', '+00:00')) if data.get('generated_at_utc') else None
                    })
                    print(f"âœ… Loaded: {filename}")
            except Exception as e:
                print(f"âŒ Error loading {filename}: {e}")
    
    return reports

def get_price_history(ticker, lookback_hours=72):
    """RÃ©cupÃ¨re le prix du token Ã  diffÃ©rents intervalles (CoinGecko)"""
    try:
        ticker_clean = ticker.lstrip("$").lower()
        
        url = "https://api.coingecko.com/api/v3/search"
        params = {"query": ticker_clean}
        r = requests.get(url, params=params, timeout=5)
        
        if r.status_code != 200:
            return None
        
        data = r.json()
        coins = data.get("coins", [])
        
        if not coins:
            return None
        
        coin = next((c for c in coins if (c.get("symbol") or "").upper() == ticker.lstrip("$").upper()), coins[0])
        coin_id = coin.get("id")
        
        if not coin_id:
            return None
        
        history_url = f"https://api.coingecko.com/api/v3/coins/{coin_id}/market_chart"
        history_params = {
            "vs_currency": "usd",
            "days": max(1, lookback_hours // 24 + 1),
            "interval": "daily"
        }
        
        r2 = requests.get(history_url, params=history_params, timeout=5)
        
        if r2.status_code != 200:
            return None
        
        return r2.json()
    
    except Exception as e:
        print(f"  Price history error {ticker}: {e}")
        return None

def calculate_return(signal_price, signal_time, target_hours, price_history):
    """Calcule le retour entre le signal et T+target_hours"""
    try:
        if not price_history or 'prices' not in price_history:
            return None
        
        prices = price_history.get('prices', [])
        
        if not prices or not signal_price or signal_price <= 0:
            return None
        
        target_time = datetime.fromisoformat(signal_time.replace('Z', '+00:00')) + timedelta(hours=target_hours)
        target_timestamp = int(target_time.timestamp() * 1000)
        
        closest_price = None
        min_diff = float('inf')
        
        for timestamp, price in prices:
            diff = abs(timestamp - target_timestamp)
            if diff < min_diff:
                min_diff = diff
                closest_price = price
        
        if closest_price is None:
            return None
        
        return ((closest_price - signal_price) / signal_price) * 100
    
    except Exception as e:
        return None

def backtest_signals(reports, lookback_hours=72):
    """Analyse l'historique des signaux"""
    
    if not reports:
        print("ERROR: No reports loaded")
        return
    
    print(f"\n{'='*80}")
    print(f"BACKTESTING {len(reports)} REPORTS (lookback: {lookback_hours}h)")
    print(f"{'='*80}\n")
    
    all_signals = []
    verdict_results = defaultdict(list)
    tier_results = defaultdict(list)
    narrative_results = defaultdict(list)
    account_results = defaultdict(list)
    
    for report in reports:
        data = report['data']
        ranked = data.get('ranked', [])
        
        print(f"Processing {len(ranked)} signals from {report['filename']}...")
        
        for signal in ranked:
            ticker = signal.get('ticker')
            score = signal.get('score')
            sentiment = signal.get('avg_sentiment')
            signal_type = signal.get('signal_type')
            current_price = signal.get('current_price_usd')
            signal_timestamp = signal.get('signal_timestamp_utc')
            authors = signal.get('authors', [])
            market_data = signal.get('market_data', {})
            gpt_analysis = signal.get('gpt_analysis')
            
            if not all([ticker, current_price, signal_timestamp]):
                continue
            
            gpt_verdict = gpt_analysis.get('verdict') if gpt_analysis else None
            
            price_history = get_price_history(ticker, lookback_hours)
            return_pct = calculate_return(current_price, signal_timestamp, lookback_hours, price_history)
            
            signal_result = {
                'ticker': ticker,
                'score': score,
                'sentiment': sentiment,
                'signal_type': signal_type,
                'signal_price': current_price,
                'return_pct': return_pct,
                'verdict': gpt_verdict,
                'confidence': gpt_analysis.get('confidence') if gpt_analysis else None,
                'authors': authors,
                'market_cap': market_data.get('market_cap_usd'),
                'success': return_pct > 0 if return_pct is not None else None,
            }
            
            all_signals.append(signal_result)
            
            if return_pct is not None:
                if gpt_verdict:
                    verdict_results[gpt_verdict].append(return_pct)
                
                for author in authors:
                    account_results[author].append(return_pct)
            
            narratives = signal.get('narratives', [])
            for narrative in narratives:
                if return_pct is not None:
                    narrative_results[narrative].append(return_pct)
    
    print(f"\n{'='*80}")
    print(f"RESULTS: Analyzed {len(all_signals)} signals")
    print(f"{'='*80}\n")
    
    successful = [s for s in all_signals if s['return_pct'] is not None and s['return_pct'] > 0]
    failed = [s for s in all_signals if s['return_pct'] is not None and s['return_pct'] <= 0]
    unknown = [s for s in all_signals if s['return_pct'] is None]
    
    print(f"âœ… Successful (+): {len(successful)} ({len(successful)/max(1, len(successful)+len(failed))*100:.1f}%)")
    print(f"âŒ Failed (-): {len(failed)}")
    print(f"â“ Unknown (no price data): {len(unknown)}")
    print()
    
    if successful:
        avg_gain = sum(s['return_pct'] for s in successful) / len(successful)
        max_gain = max(s['return_pct'] for s in successful)
        print(f"Average gain (successful): {avg_gain:+.2f}%")
        print(f"Best trade: {max_gain:+.2f}%")
        print()
    
    if failed:
        avg_loss = sum(s['return_pct'] for s in failed) / len(failed)
        max_loss = min(s['return_pct'] for s in failed)
        print(f"Average loss (failed): {avg_loss:+.2f}%")
        print(f"Worst trade: {max_loss:+.2f}%")
        print()
    
    if verdict_results:
        print(f"PERFORMANCE BY GPT VERDICT:")
        print("-" * 80)
        for verdict, returns in sorted(verdict_results.items()):
            if returns:
                win_count = len([r for r in returns if r > 0])
                win_rate = win_count / len(returns) * 100
                avg_return = sum(returns) / len(returns)
                print(f"  {verdict}: {len(returns)} signals | Win rate: {win_rate:.1f}% | Avg return: {avg_return:+.2f}%")
        print()
    
    if narrative_results:
        print(f"PERFORMANCE BY NARRATIVE:")
        print("-" * 80)
        for narrative, returns in sorted(narrative_results.items(), key=lambda x: len(x[1]), reverse=True)[:5]:
            if returns:
                win_count = len([r for r in returns if r > 0])
                win_rate = win_count / len(returns) * 100
                avg_return = sum(returns) / len(returns)
                print(f"  {narrative}: {len(returns)} signals | Win rate: {win_rate:.1f}% | Avg return: {avg_return:+.2f}%")
        print()
    
    if account_results:
        print(f"PERFORMANCE BY ACCOUNT (Top 10):")
        print("-" * 80)
        sorted_accounts = sorted(account_results.items(), key=lambda x: len(x[1]), reverse=True)
        for account, returns in sorted_accounts[:10]:
            if returns:
                win_count = len([r for r in returns if r > 0])
                win_rate = win_count / len(returns) * 100
                avg_return = sum(returns) / len(returns)
                print(f"  @{account}: {len(returns)} signals | Win rate: {win_rate:.1f}% | Avg return: {avg_return:+.2f}%")
        print()
    
    print(f"TOP SIGNALS (by return):")
    print("-" * 80)
    sorted_signals = sorted([s for s in all_signals if s['return_pct'] is not None], key=lambda x: x['return_pct'], reverse=True)
    for signal in sorted_signals[:10]:
        verdict_str = f"[{signal['verdict']}]" if signal['verdict'] else ""
        print(f"  {signal['ticker']} {verdict_str}: {signal['return_pct']:+.2f}% | Score: {signal['score']}/100 | Sentiment: {signal['sentiment']:+.2f}")
    print()
    
    print(f"WORST SIGNALS (by return):")
    print("-" * 80)
    for signal in sorted_signals[-10:]:
        verdict_str = f"[{signal['verdict']}]" if signal['verdict'] else ""
        print(f"  {signal['ticker']} {verdict_str}: {signal['return_pct']:+.2f}% | Score: {signal['score']}/100 | Sentiment: {signal['sentiment']:+.2f}")
    print()
    
    summary = {
        'total_signals': len(all_signals),
        'successful': len(successful),
        'failed': len(failed),
        'unknown': len(unknown),
        'win_rate': len(successful) / max(1, len(successful) + len(failed)) * 100,
        'verdict_performance': {k: {
            'signals': len(v),
            'avg_return': sum(v) / len(v),
            'win_rate': len([r for r in v if r > 0]) / len(v) * 100
        } for k, v in verdict_results.items()},
        'all_signals': [
            {
                'ticker': s['ticker'],
                'score': s['score'],
                'verdict': s['verdict'],
                'return_pct': s['return_pct'],
                'success': s['success']
            } for s in all_signals
        ]
    }
    
    output_json = os.path.join(reports_dir, 'backtest_results_v91.json')
    with open(output_json, 'w', encoding='utf-8') as f:
        json.dump(summary, f, indent=2)
    print(f"\nâœ… Results saved to: {output_json}")

def main():
    parser = argparse.ArgumentParser(description='Crypto X Agent V9.1 Backtesting')
    parser.add_argument('--reports', default='reports', help='Directory with JSON reports')
    parser.add_argument('--lookback', default='72h', help='Lookback period (e.g. 24h, 48h, 72h)')
    args = parser.parse_args()
    
    lookback_hours = int(args.lookback.replace('h', ''))
    
    reports = load_all_reports(args.reports)
    
    if not reports:
        print("No reports found. Collect 15 days of data first.")
        sys.exit(1)
    
    backtest_signals(reports, lookback_hours)

if __name__ == '__main__':
    main()

