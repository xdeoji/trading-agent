#!/usr/bin/env python3
"""Fetch full trading state: balance, markets, positions, orders, recent trades.

Calls GET /api/state/:address
"""

import argparse
import json
import sys

import requests

from _config import load_config, get_address_from_key, require_private_key, output, error_exit


def main():
    parser = argparse.ArgumentParser(description="Fetch full trading state from the exchange")
    parser.add_argument("--address", help="Wallet address (derived from PRIVATE_KEY if omitted)")
    args = parser.parse_args()

    cfg = load_config()

    if args.address:
        address = args.address
    else:
        pk = require_private_key(cfg)
        address = get_address_from_key(pk)

    url = f"{cfg['EXCHANGE_URL']}/api/state/{address}"

    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        data["success"] = True
        output(data)
    except requests.RequestException as e:
        error_exit(f"Failed to fetch state: {e}")


if __name__ == "__main__":
    main()
