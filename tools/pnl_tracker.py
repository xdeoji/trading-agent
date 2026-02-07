#!/usr/bin/env python3
"""Track positions and calculate P&L.

Fetches state via /api/state/:address and computes unrealized P&L from positions vs fair prices.
"""

import argparse
import json
import sys

import requests

from _config import load_config, get_address_from_key, require_private_key, output, error_exit

PRICE_PRECISION = 10000
USDC_DECIMALS = 6


def main():
    parser = argparse.ArgumentParser(description="Track positions and calculate P&L")
    parser.add_argument("--address", help="Wallet address (derived from PRIVATE_KEY if omitted)")
    args = parser.parse_args()

    cfg = load_config()

    if args.address:
        address = args.address
    else:
        pk = require_private_key(cfg)
        address = get_address_from_key(pk)

    base_url = cfg["EXCHANGE_URL"]

    # Fetch full state
    try:
        resp = requests.get(f"{base_url}/api/state/{address}", timeout=10)
        resp.raise_for_status()
        state = resp.json()
    except requests.RequestException as e:
        error_exit(f"Failed to fetch state: {e}")

    positions = state.get("positions", {})
    markets = state.get("markets", [])

    # Build market lookup
    market_map = {}
    for m in markets:
        mid = m.get("marketId") or m.get("id")
        if mid is not None:
            market_map[str(mid)] = m

    # Calculate P&L for each position
    position_details = []
    total_unrealized_pnl = 0.0

    for market_id_str, pos in positions.items():
        yes_shares_raw = int(pos.get("yes", pos.get("yesShares", 0)))
        no_shares_raw = int(pos.get("no", pos.get("noShares", 0)))

        if yes_shares_raw == 0 and no_shares_raw == 0:
            continue

        yes_shares = yes_shares_raw / 10 ** USDC_DECIMALS
        no_shares = no_shares_raw / 10 ** USDC_DECIMALS

        # Fetch fair price for this market
        yes_fair_price = 0.5  # default
        no_fair_price = 0.5
        try:
            fp_resp = requests.get(f"{base_url}/api/fair-price/{market_id_str}", timeout=5)
            if fp_resp.status_code == 200:
                fp = fp_resp.json()
                yes_fair_price = fp.get("yesFairPrice", 5000) / PRICE_PRECISION
                no_fair_price = fp.get("noFairPrice", 5000) / PRICE_PRECISION
        except requests.RequestException:
            pass

        # Unrealized P&L: current value of shares minus what we'd get if market resolved at current price
        # YES shares are worth yesFairPrice each, NO shares are worth noFairPrice each
        yes_value = yes_shares * yes_fair_price
        no_value = no_shares * no_fair_price
        total_value = yes_value + no_value

        detail = {
            "marketId": int(market_id_str),
            "yesShares": yes_shares,
            "noShares": no_shares,
            "yesFairPrice": round(yes_fair_price, 4),
            "noFairPrice": round(no_fair_price, 4),
            "yesValue": round(yes_value, 2),
            "noValue": round(no_value, 2),
            "totalValue": round(total_value, 2),
        }
        position_details.append(detail)
        total_unrealized_pnl += total_value

    # Balance info
    balance = state.get("balance", {})
    available = int(balance.get("available", 0)) / 10 ** USDC_DECIMALS
    reserved = int(balance.get("reserved", 0)) / 10 ** USDC_DECIMALS

    output({
        "success": True,
        "address": address,
        "balance": {
            "available": round(available, 2),
            "reserved": round(reserved, 2),
        },
        "totalPositionValue": round(total_unrealized_pnl, 2),
        "positionCount": len(position_details),
        "positions": position_details,
        "openOrderCount": len(state.get("openOrders", [])),
    })


if __name__ == "__main__":
    main()
