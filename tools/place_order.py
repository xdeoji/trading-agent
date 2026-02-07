#!/usr/bin/env python3
"""Sign an EIP-712 order and submit it to the exchange.

Constructs the order, signs with eth_account, and POSTs to /api/order.
"""

import argparse
import json
import sys
import time

import requests
from eth_account import Account

from _config import load_config, require_private_key, output, error_exit
from sign_order import sign_order

PRICE_PRECISION = 10000
USDC_DECIMALS = 6


def main():
    parser = argparse.ArgumentParser(description="Place a signed order on the exchange")
    parser.add_argument("--market-id", type=int, required=True, help="Market ID")
    parser.add_argument("--side", required=True, choices=["buy", "sell"], help="Order side")
    parser.add_argument("--outcome", required=True, choices=["yes", "no"], help="YES or NO shares")
    parser.add_argument("--price", type=float, required=True, help="Price as decimal 0-1 (e.g. 0.55 = 55 cents)")
    parser.add_argument("--amount", type=float, required=True, help="Amount in USDC (e.g. 10 = $10 = 10 shares)")
    parser.add_argument("--nonce", type=int, help="Order nonce (default: timestamp ms)")
    parser.add_argument("--expiry", type=int, help="Expiry unix timestamp (default: +1 hour)")
    args = parser.parse_args()

    cfg = load_config()
    pk = require_private_key(cfg)
    account = Account.from_key(pk)

    # Validate price range
    if args.price <= 0 or args.price >= 1:
        error_exit("Price must be between 0 and 1 (exclusive)")

    price_bps = int(args.price * PRICE_PRECISION)
    amount_raw = int(args.amount * 10 ** USDC_DECIMALS)
    nonce = args.nonce or int(time.time() * 1000)
    expiry = args.expiry or (int(time.time()) + 3600)

    # Sign the order
    signed = sign_order(
        cfg, account,
        market_id=args.market_id,
        is_buy=(args.side == "buy"),
        is_yes=(args.outcome == "yes"),
        price_bps=price_bps,
        amount_raw=amount_raw,
        nonce=nonce,
        expiry=expiry,
    )

    # Submit to exchange
    url = f"{cfg['EXCHANGE_URL']}/api/order"
    try:
        resp = requests.post(url, json={"order": signed}, timeout=10)
        data = resp.json()
        output(data)
    except requests.RequestException as e:
        error_exit(f"Failed to submit order: {e}")


if __name__ == "__main__":
    main()
