#!/usr/bin/env python3
"""Withdraw USDC from vault and transfer to a pre-configured personal wallet.

SECURITY: This tool transfers real funds. To prevent prompt injection attacks
(e.g. a malicious market name tricking the LLM into sending funds to an
attacker), the destination address MUST be pre-configured in agent.env as
WITHDRAW_TO. The --to flag is only accepted if it matches WITHDRAW_TO.

Setup:
  Add to agent.env:  WITHDRAW_TO=0xYourPersonalWallet

Usage:
  python3 ./tools/cashout.py                          # dry run: show what would happen
  python3 ./tools/cashout.py --confirm                # transfer all to WITHDRAW_TO
  python3 ./tools/cashout.py --amount 50 --confirm    # transfer 50 USDC
  python3 ./tools/cashout.py --to 0x... --confirm     # must match WITHDRAW_TO
"""

import argparse
import json
import sys
import os

from _config import load_config, require_private_key, get_address_from_key, output, error_exit

USDC_DECIMALS = 6

ERC20_ABI = [
    {
        "inputs": [{"name": "account", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [
            {"name": "to", "type": "address"},
            {"name": "amount", "type": "uint256"},
        ],
        "name": "transfer",
        "outputs": [{"name": "", "type": "bool"}],
        "stateMutability": "nonpayable",
        "type": "function",
    },
]

VAULT_ABI = [
    {
        "inputs": [{"name": "user", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [{"name": "amount", "type": "uint256"}],
        "name": "withdraw",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    },
]


def main():
    parser = argparse.ArgumentParser(
        description="Withdraw USDC and transfer to your personal wallet"
    )
    parser.add_argument(
        "--to",
        help="Destination address (must match WITHDRAW_TO in agent.env)",
    )
    parser.add_argument(
        "--amount", type=float,
        help="USDC amount to transfer (default: all available)",
    )
    parser.add_argument(
        "--confirm", action="store_true",
        help="Actually execute the transfer (default: dry run only)",
    )
    args = parser.parse_args()

    cfg = load_config()
    pk = require_private_key(cfg)

    # ── Resolve destination from trusted source ──────────────────
    withdraw_to = os.environ.get("WITHDRAW_TO", "").strip()

    if not withdraw_to:
        error_exit(
            "WITHDRAW_TO not configured. For security, the destination address must be "
            "set in agent.env (not provided by the AI). Add this line to agent.env:\n"
            "  WITHDRAW_TO=0xYourPersonalWalletAddress\n"
            "Then run this tool again."
        )

    # Validate WITHDRAW_TO is a valid address
    try:
        from web3 import Web3
        withdraw_to = Web3.to_checksum_address(withdraw_to)
    except Exception:
        error_exit(f"WITHDRAW_TO is not a valid Ethereum address: {withdraw_to}")

    # If --to is provided, it MUST match WITHDRAW_TO
    if args.to:
        try:
            provided = Web3.to_checksum_address(args.to)
        except Exception:
            error_exit(f"--to is not a valid Ethereum address: {args.to}")

        if provided != withdraw_to:
            error_exit(
                f"Address mismatch: --to {provided} does not match WITHDRAW_TO {withdraw_to}. "
                "For security, transfers can only go to the pre-configured WITHDRAW_TO address. "
                "If you need to change the destination, update WITHDRAW_TO in agent.env."
            )

    # ── Connect and check balances ───────────────────────────────
    w3 = Web3(Web3.HTTPProvider(cfg["RPC_URL"]))
    if not w3.is_connected():
        error_exit(f"Cannot connect to RPC: {cfg['RPC_URL']}")

    account = w3.eth.account.from_key(pk)
    agent_address = account.address

    vault_addr = Web3.to_checksum_address(cfg["VAULT_ADDRESS"])
    usdc_addr = Web3.to_checksum_address(cfg["USDC_ADDRESS"])

    vault = w3.eth.contract(address=vault_addr, abi=VAULT_ABI)
    usdc = w3.eth.contract(address=usdc_addr, abi=ERC20_ABI)

    vault_bal = vault.functions.balanceOf(agent_address).call()
    wallet_bal = usdc.functions.balanceOf(agent_address).call()

    vault_usdc = vault_bal / 10**USDC_DECIMALS
    wallet_usdc = wallet_bal / 10**USDC_DECIMALS

    # ── Determine transfer amount ────────────────────────────────
    total_available = vault_bal + wallet_bal

    if args.amount is not None:
        if args.amount <= 0:
            error_exit("--amount must be positive")
        transfer_raw = int(args.amount * 10**USDC_DECIMALS)
        if transfer_raw > total_available:
            error_exit(
                f"Requested {args.amount} USDC but only {total_available / 10**USDC_DECIMALS:.2f} "
                f"available (vault: {vault_usdc:.2f}, wallet: {wallet_usdc:.2f})"
            )
    else:
        transfer_raw = total_available

    if transfer_raw == 0:
        error_exit("No USDC available to transfer (vault and wallet both empty)")

    transfer_usdc = transfer_raw / 10**USDC_DECIMALS

    # How much needs to come from vault vs wallet
    need_from_vault = max(0, transfer_raw - wallet_bal)
    will_send = transfer_raw

    # ── Dry run (default) ────────────────────────────────────────
    plan = {
        "success": True,
        "dryRun": not args.confirm,
        "from": agent_address,
        "to": withdraw_to,
        "transferUSDC": round(transfer_usdc, 2),
        "vaultBalance": round(vault_usdc, 2),
        "walletBalance": round(wallet_usdc, 2),
    }

    if need_from_vault > 0:
        plan["vaultWithdrawUSDC"] = round(need_from_vault / 10**USDC_DECIMALS, 2)
        plan["steps"] = [
            f"1. Withdraw {need_from_vault / 10**USDC_DECIMALS:.2f} USDC from vault to agent wallet",
            f"2. Transfer {transfer_usdc:.2f} USDC from agent wallet to {withdraw_to}",
        ]
    else:
        plan["steps"] = [
            f"1. Transfer {transfer_usdc:.2f} USDC from agent wallet to {withdraw_to}",
        ]

    if not args.confirm:
        plan["message"] = "DRY RUN — no funds moved. Run with --confirm to execute."
        output(plan)
        return

    # ── Execute ──────────────────────────────────────────────────
    def send_tx(tx_data):
        signed = account.sign_transaction(tx_data)
        tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
        return w3.eth.wait_for_transaction_receipt(tx_hash)

    tx_hashes = []

    # Step 1: Withdraw from vault if needed
    if need_from_vault > 0:
        print(f"Withdrawing {need_from_vault / 10**USDC_DECIMALS:.2f} USDC from vault...", file=sys.stderr)
        withdraw_tx = vault.functions.withdraw(need_from_vault).build_transaction({
            "from": agent_address,
            "nonce": w3.eth.get_transaction_count(agent_address),
            "gas": 200000,
        })
        receipt = send_tx(withdraw_tx)
        tx_hashes.append(receipt.transactionHash.hex())

    # Step 2: Transfer USDC to personal wallet
    print(f"Transferring {transfer_usdc:.2f} USDC to {withdraw_to}...", file=sys.stderr)
    transfer_tx = usdc.functions.transfer(withdraw_to, will_send).build_transaction({
        "from": agent_address,
        "nonce": w3.eth.get_transaction_count(agent_address),
        "gas": 100000,
    })
    receipt = send_tx(transfer_tx)
    tx_hashes.append(receipt.transactionHash.hex())

    # Final balances
    final_vault = vault.functions.balanceOf(agent_address).call()
    final_wallet = usdc.functions.balanceOf(agent_address).call()

    output({
        "success": True,
        "dryRun": False,
        "transferred": round(transfer_usdc, 2),
        "to": withdraw_to,
        "txHashes": tx_hashes,
        "remainingVault": round(final_vault / 10**USDC_DECIMALS, 2),
        "remainingWallet": round(final_wallet / 10**USDC_DECIMALS, 2),
    })


if __name__ == "__main__":
    main()
