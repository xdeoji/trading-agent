#!/usr/bin/env python3
"""Standalone EIP-712 and EIP-191 signing utility.

Signs orders (EIP-712) or cancel messages (EIP-191) without submitting them.
"""

import argparse
import json
import sys
import time

from eth_account import Account
from eth_account.messages import encode_defunct, encode_typed_data

from _config import load_config, require_private_key, output, error_exit

PRICE_PRECISION = 10000
USDC_DECIMALS = 6


def build_eip712_domain(cfg: dict) -> dict:
    return {
        "name": "BlackjackExchange",
        "version": "1",
        "chainId": cfg["CHAIN_ID"],
        "verifyingContract": cfg["EXCHANGE_ADDRESS"],
    }


ORDER_TYPES = {
    "Order": [
        {"name": "trader", "type": "address"},
        {"name": "marketId", "type": "uint64"},
        {"name": "isBuy", "type": "bool"},
        {"name": "isYes", "type": "bool"},
        {"name": "price", "type": "uint64"},
        {"name": "amount", "type": "uint128"},
        {"name": "nonce", "type": "uint64"},
        {"name": "expiry", "type": "uint64"},
    ]
}


def sign_order(cfg: dict, account: Account, market_id: int, is_buy: bool, is_yes: bool,
               price_bps: int, amount_raw: int, nonce: int, expiry: int) -> dict:
    """Sign an order with EIP-712 and return the signed order payload."""
    domain = build_eip712_domain(cfg)
    address = account.address

    message_data = {
        "trader": address,
        "marketId": market_id,
        "isBuy": is_buy,
        "isYes": is_yes,
        "price": price_bps,
        "amount": amount_raw,
        "nonce": nonce,
        "expiry": expiry,
    }

    signable = encode_typed_data(
        domain_data=domain,
        message_types={"Order": ORDER_TYPES["Order"]},
        message_data=message_data,
    )
    signed = account.sign_message(signable)

    return {
        "trader": address,
        "marketId": market_id,
        "isBuy": is_buy,
        "isYes": is_yes,
        "price": price_bps,
        "amount": str(amount_raw),
        "nonce": nonce,
        "expiry": expiry,
        "signature": _hex_sig(signed.signature),
    }


def _hex_sig(sig) -> str:
    """Ensure signature has 0x prefix."""
    h = sig.hex() if isinstance(sig, bytes) else str(sig)
    return h if h.startswith("0x") else f"0x{h}"


def sign_cancel(account: Account, order_id: str) -> dict:
    """Sign a cancel message with EIP-191."""
    timestamp = int(time.time() * 1000)
    message = f"Cancel order {order_id}\nTimestamp: {timestamp}"
    signable = encode_defunct(text=message)
    signed = account.sign_message(signable)

    return {
        "orderId": order_id,
        "message": message,
        "timestamp": timestamp,
        "signature": _hex_sig(signed.signature),
    }


def main():
    parser = argparse.ArgumentParser(description="Sign orders (EIP-712) or cancel messages (EIP-191)")
    parser.add_argument("--type", required=True, choices=["order", "cancel"], help="What to sign")

    # Order fields
    parser.add_argument("--market-id", type=int, help="Market ID (for order)")
    parser.add_argument("--side", choices=["buy", "sell"], help="Order side (for order)")
    parser.add_argument("--outcome", choices=["yes", "no"], help="YES or NO shares (for order)")
    parser.add_argument("--price", type=float, help="Price as decimal 0-1 (for order)")
    parser.add_argument("--amount", type=float, help="Amount in USDC (for order)")
    parser.add_argument("--nonce", type=int, help="Order nonce (default: timestamp ms)")
    parser.add_argument("--expiry", type=int, help="Expiry unix timestamp (default: +1 hour)")

    # Cancel fields
    parser.add_argument("--order-id", help="Order ID to cancel (for cancel)")

    args = parser.parse_args()
    cfg = load_config()
    pk = require_private_key(cfg)
    account = Account.from_key(pk)

    if args.type == "order":
        if not all([args.market_id is not None, args.side, args.outcome, args.price is not None, args.amount is not None]):
            error_exit("Order signing requires: --market-id, --side, --outcome, --price, --amount")

        price_bps = int(args.price * PRICE_PRECISION)
        amount_raw = int(args.amount * 10 ** USDC_DECIMALS)
        nonce = args.nonce or int(time.time() * 1000)
        expiry = args.expiry or (int(time.time()) + 3600)

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
        output({"success": True, "type": "order", "signedOrder": signed})

    elif args.type == "cancel":
        if not args.order_id:
            error_exit("Cancel signing requires: --order-id")

        signed = sign_cancel(account, args.order_id)
        output({"success": True, "type": "cancel", **signed})


if __name__ == "__main__":
    main()
