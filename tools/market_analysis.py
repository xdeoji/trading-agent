#!/usr/bin/env python3
"""Analyze markets for trading opportunities.

Surfaces raw edge signals: mispricings, arbitrage, spread capture opportunities,
liquidity depth, and volume. Does NOT make recommendations — the agent decides.

Fetches from /api/fair-price/:marketId, /api/orderbook/:marketId, /api/market-stats/:marketId.
If no --market-id is given, analyzes all active markets.
"""

import argparse
import json
import sys

import requests

from _config import load_config, output, error_exit

PRICE_PRECISION = 10000
USDC_DECIMALS = 6


def analyze_market(base_url: str, market_id: int) -> dict:
    """Analyze a single market and return raw edge signals."""
    result = {"marketId": market_id}

    # ---- Fair price + spread data ----
    try:
        resp = requests.get(f"{base_url}/api/fair-price/{market_id}", timeout=10)
        if resp.status_code == 200:
            fp = resp.json()
            result["yesBestBid"] = fp.get("yesBestBid")
            result["yesBestAsk"] = fp.get("yesBestAsk")
            result["noBestBid"] = fp.get("noBestBid")
            result["noBestAsk"] = fp.get("noBestAsk")
            result["yesFairPrice"] = fp.get("yesFairPrice")
            result["noFairPrice"] = fp.get("noFairPrice")
            result["hasLiquidity"] = fp.get("hasLiquidity", False)

            # Human-readable conversions
            for key in ("yesFairPrice", "noFairPrice", "yesBestBid", "yesBestAsk", "noBestBid", "noBestAsk"):
                val = result.get(key)
                if val is not None:
                    result[f"{key}Pct"] = round(val / PRICE_PRECISION * 100, 2)

            # ---- Spread analysis ----
            yes_bid = result.get("yesBestBid")
            yes_ask = result.get("yesBestAsk")
            no_bid = result.get("noBestBid")
            no_ask = result.get("noBestAsk")

            if yes_bid and yes_ask:
                result["yesSpread"] = yes_ask - yes_bid
                result["yesSpreadPct"] = round((yes_ask - yes_bid) / PRICE_PRECISION * 100, 2)
            if no_bid and no_ask:
                result["noSpread"] = no_ask - no_bid
                result["noSpreadPct"] = round((no_ask - no_bid) / PRICE_PRECISION * 100, 2)

            # ---- Arbitrage signals ----
            # YES ask + NO ask = cost to buy both sides. If < 10000, free money.
            if yes_ask and no_ask:
                buy_both_cost = yes_ask + no_ask
                result["buyBothCost"] = buy_both_cost
                result["buyBothCostPct"] = round(buy_both_cost / PRICE_PRECISION * 100, 2)
                result["arbBuyBoth"] = round((PRICE_PRECISION - buy_both_cost) / PRICE_PRECISION * 100, 2)

            # YES bid + NO bid = revenue from selling both sides. If > 10000, free money (mint + sell).
            if yes_bid and no_bid:
                sell_both_revenue = yes_bid + no_bid
                result["sellBothRevenue"] = sell_both_revenue
                result["sellBothRevenuePct"] = round(sell_both_revenue / PRICE_PRECISION * 100, 2)
                result["arbMintSell"] = round((sell_both_revenue - PRICE_PRECISION) / PRICE_PRECISION * 100, 2)

            # Fair price sum check — should be ~100%. Deviation means mispricing.
            yes_fair = result.get("yesFairPrice")
            no_fair = result.get("noFairPrice")
            if yes_fair and no_fair:
                result["yesNoSum"] = yes_fair + no_fair
                result["yesNoSumPct"] = round((yes_fair + no_fair) / PRICE_PRECISION * 100, 2)

            # ---- Market making opportunity ----
            # Spread capture: if you can buy at bid and sell at ask, profit per share
            if yes_bid and yes_ask:
                result["yesSpreadCapture"] = round((yes_ask - yes_bid) / PRICE_PRECISION, 4)
            if no_bid and no_ask:
                result["noSpreadCapture"] = round((no_ask - no_bid) / PRICE_PRECISION, 4)

    except requests.RequestException:
        result["fairPriceError"] = "Failed to fetch fair price"

    # ---- Orderbook depth ----
    try:
        resp = requests.get(f"{base_url}/api/orderbook/{market_id}", timeout=10)
        if resp.status_code == 200:
            book = resp.json()
            result["orderbook"] = {
                "yesBidLevels": len(book.get("yesBids", [])),
                "yesAskLevels": len(book.get("yesAsks", [])),
                "noBidLevels": len(book.get("noBids", [])),
                "noAskLevels": len(book.get("noAsks", [])),
            }

            # Total depth in USDC
            for side_key, levels in [("yesBidDepth", book.get("yesBids", [])),
                                      ("yesAskDepth", book.get("yesAsks", [])),
                                      ("noBidDepth", book.get("noBids", [])),
                                      ("noAskDepth", book.get("noAsks", []))]:
                total = sum(int(lvl.get("totalAmount", 0)) for lvl in levels)
                result["orderbook"][side_key] = round(total / 10 ** USDC_DECIMALS, 2)

            # Top-of-book size (how much you can fill at best price)
            for side_key, levels in [("yesBidTopSize", book.get("yesBids", [])),
                                      ("yesAskTopSize", book.get("yesAsks", [])),
                                      ("noBidTopSize", book.get("noBids", [])),
                                      ("noAskTopSize", book.get("noAsks", []))]:
                top = int(levels[0]["totalAmount"]) / 10 ** USDC_DECIMALS if levels else 0
                result["orderbook"][side_key] = round(top, 2)

    except requests.RequestException:
        result["orderbookError"] = "Failed to fetch orderbook"

    # ---- Market stats ----
    try:
        resp = requests.get(f"{base_url}/api/market-stats/{market_id}", timeout=10)
        if resp.status_code == 200:
            stats = resp.json()
            result["volume"] = round(int(stats.get("volume", "0")) / 10 ** USDC_DECIMALS, 2)
            result["tradeCount"] = stats.get("tradeCount", 0)
            result["lastTradePrice"] = stats.get("lastTradePrice")
            result["phase"] = stats.get("phase")
            result["handId"] = stats.get("handId")
    except requests.RequestException:
        result["statsError"] = "Failed to fetch market stats"

    return result


def main():
    parser = argparse.ArgumentParser(description="Analyze markets for trading opportunities")
    parser.add_argument("--market-id", type=int, help="Market ID (omit to analyze all active markets)")
    args = parser.parse_args()

    cfg = load_config()
    base_url = cfg["EXCHANGE_URL"]

    if args.market_id is not None:
        result = analyze_market(base_url, args.market_id)
        output({"success": True, "markets": [result]})
    else:
        # Fetch all active markets
        try:
            resp = requests.get(f"{base_url}/api/markets", timeout=10)
            resp.raise_for_status()
            markets_data = resp.json()
            market_list = markets_data.get("markets", [])
        except requests.RequestException as e:
            error_exit(f"Failed to fetch markets: {e}")

        if not market_list:
            output({"success": True, "markets": [], "message": "No active markets"})
            return

        results = []
        for m in market_list:
            mid = m.get("marketId") or m.get("id")
            if mid is not None:
                results.append(analyze_market(base_url, mid))

        output({"success": True, "markets": results})


if __name__ == "__main__":
    main()
