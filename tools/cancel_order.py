#!/usr/bin/env python3
"""Cancel an order on the exchange with an EIP-191 signed message.

Signs `Cancel order {orderId}\\nTimestamp: {timestamp}` and DELETEs /api/order/:orderId.
"""

import argparse
import json
import sys

import requests
from eth_account import Account

from _config import load_config, require_private_key, output, error_exit
from sign_order import sign_cancel


def main():
    parser = argparse.ArgumentParser(description="Cancel an order on the exchange")
    parser.add_argument("--order-id", required=True, help="Order ID to cancel")
    args = parser.parse_args()

    cfg = load_config()
    pk = require_private_key(cfg)
    account = Account.from_key(pk)

    # Sign the cancel message
    cancel_data = sign_cancel(account, args.order_id)

    # Submit cancel to exchange
    url = f"{cfg['EXCHANGE_URL']}/api/order/{args.order_id}"
    try:
        resp = requests.delete(
            url,
            json={
                "signature": cancel_data["signature"],
                "message": cancel_data["message"],
                "timestamp": cancel_data["timestamp"],
            },
            timeout=10,
        )
        data = resp.json()
        output(data)
    except requests.RequestException as e:
        error_exit(f"Failed to cancel order: {e}")


if __name__ == "__main__":
    main()
