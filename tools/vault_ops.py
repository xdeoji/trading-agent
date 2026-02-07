#!/usr/bin/env python3
"""On-chain operations: Vault (deposit/withdraw/balance) and Exchange (mint/merge/claim shares).

Uses web3.py to interact with contracts directly on Monad.

Actions:
  balance   - Check vault balance + wallet USDC
  deposit   - Deposit USDC into Vault (auto-approves if needed)
  withdraw  - Withdraw USDC from Vault
  mint      - Mint YES+NO share pairs on Exchange (costs USDC from vault)
  merge     - Merge YES+NO pairs back to USDC
  claim     - Claim winnings from a resolved market
"""

import argparse
import json
import sys

from _config import load_config, require_private_key, get_address_from_key, output, error_exit

USDC_DECIMALS = 6

VAULT_ABI = [
    {
        "inputs": [{"name": "amount", "type": "uint256"}],
        "name": "deposit",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "inputs": [{"name": "amount", "type": "uint256"}],
        "name": "withdraw",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "inputs": [{"name": "user", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    },
]

EXCHANGE_ABI = [
    {
        "inputs": [
            {"name": "marketId", "type": "uint64"},
            {"name": "amount", "type": "uint128"},
        ],
        "name": "mintShares",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "inputs": [
            {"name": "marketId", "type": "uint64"},
            {"name": "amount", "type": "uint128"},
        ],
        "name": "mergeShares",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "inputs": [{"name": "marketId", "type": "uint64"}],
        "name": "claimWinnings",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "inputs": [
            {"name": "marketId", "type": "uint64"},
            {"name": "user", "type": "address"},
        ],
        "name": "yesShares",
        "outputs": [{"name": "", "type": "uint128"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [
            {"name": "marketId", "type": "uint64"},
            {"name": "user", "type": "address"},
        ],
        "name": "noShares",
        "outputs": [{"name": "", "type": "uint128"}],
        "stateMutability": "view",
        "type": "function",
    },
]

ERC20_ABI = [
    {
        "inputs": [
            {"name": "spender", "type": "address"},
            {"name": "amount", "type": "uint256"},
        ],
        "name": "approve",
        "outputs": [{"name": "", "type": "bool"}],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "inputs": [
            {"name": "owner", "type": "address"},
            {"name": "spender", "type": "address"},
        ],
        "name": "allowance",
        "outputs": [{"name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [{"name": "account", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    },
]


def main():
    parser = argparse.ArgumentParser(
        description="On-chain operations: vault (deposit/withdraw/balance) and exchange (mint/merge/claim)"
    )
    parser.add_argument(
        "--action", required=True,
        choices=["deposit", "withdraw", "balance", "mint", "merge", "claim"],
        help="Action to perform",
    )
    parser.add_argument("--amount", type=float, help="Amount in USDC (for deposit/withdraw/mint/merge)")
    parser.add_argument("--market-id", type=int, help="Market ID (required for mint/merge/claim)")
    parser.add_argument("--address", help="Address to check (default: derived from PRIVATE_KEY)")
    args = parser.parse_args()

    cfg = load_config()

    try:
        from web3 import Web3
    except ImportError:
        error_exit("web3 package not installed. Run: pip install web3")

    w3 = Web3(Web3.HTTPProvider(cfg["RPC_URL"]))
    if not w3.is_connected():
        error_exit(f"Cannot connect to RPC: {cfg['RPC_URL']}")

    vault_addr = Web3.to_checksum_address(cfg["VAULT_ADDRESS"])
    exchange_addr = Web3.to_checksum_address(cfg["EXCHANGE_ADDRESS"])
    usdc_addr = Web3.to_checksum_address(cfg["USDC_ADDRESS"])

    vault = w3.eth.contract(address=vault_addr, abi=VAULT_ABI)
    exchange = w3.eth.contract(address=exchange_addr, abi=EXCHANGE_ABI)
    usdc = w3.eth.contract(address=usdc_addr, abi=ERC20_ABI)

    # ---- Balance (read-only) ----
    if args.action == "balance":
        if args.address:
            address = Web3.to_checksum_address(args.address)
        else:
            pk = require_private_key(cfg)
            address = Web3.to_checksum_address(get_address_from_key(pk))

        vault_bal = vault.functions.balanceOf(address).call()
        wallet_bal = usdc.functions.balanceOf(address).call()

        result = {
            "success": True,
            "action": "balance",
            "address": address,
            "vaultBalance": round(vault_bal / 10 ** USDC_DECIMALS, 6),
            "vaultBalanceRaw": str(vault_bal),
            "walletUSDC": round(wallet_bal / 10 ** USDC_DECIMALS, 6),
            "walletUSDCRaw": str(wallet_bal),
        }

        # If market-id provided, also show share balances
        if args.market_id is not None:
            yes = exchange.functions.yesShares(args.market_id, address).call()
            no = exchange.functions.noShares(args.market_id, address).call()
            result["shares"] = {
                "marketId": args.market_id,
                "yes": round(yes / 10 ** USDC_DECIMALS, 6),
                "yesRaw": str(yes),
                "no": round(no / 10 ** USDC_DECIMALS, 6),
                "noRaw": str(no),
            }

        output(result)
        return

    # ---- All other actions require private key ----
    pk = require_private_key(cfg)
    account = w3.eth.account.from_key(pk)
    address = account.address

    def send_tx(tx_data):
        """Sign, send, and wait for a transaction."""
        signed = account.sign_transaction(tx_data)
        tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
        return w3.eth.wait_for_transaction_receipt(tx_hash)

    # ---- Deposit ----
    if args.action == "deposit":
        if args.amount is None or args.amount <= 0:
            error_exit("--amount is required and must be positive for deposit")

        amount_raw = int(args.amount * 10 ** USDC_DECIMALS)

        # Auto-approve if needed
        allowance = usdc.functions.allowance(address, vault_addr).call()
        if allowance < amount_raw:
            approve_tx = usdc.functions.approve(vault_addr, 2 ** 256 - 1).build_transaction({
                "from": address,
                "nonce": w3.eth.get_transaction_count(address),
                "gas": 100000,
            })
            send_tx(approve_tx)

        deposit_tx = vault.functions.deposit(amount_raw).build_transaction({
            "from": address,
            "nonce": w3.eth.get_transaction_count(address),
            "gas": 200000,
        })
        receipt = send_tx(deposit_tx)
        new_bal = vault.functions.balanceOf(address).call()

        output({
            "success": True,
            "action": "deposit",
            "amount": args.amount,
            "txHash": receipt.transactionHash.hex(),
            "newBalance": round(new_bal / 10 ** USDC_DECIMALS, 6),
        })

    # ---- Withdraw ----
    elif args.action == "withdraw":
        if args.amount is None or args.amount <= 0:
            error_exit("--amount is required and must be positive for withdraw")

        amount_raw = int(args.amount * 10 ** USDC_DECIMALS)

        withdraw_tx = vault.functions.withdraw(amount_raw).build_transaction({
            "from": address,
            "nonce": w3.eth.get_transaction_count(address),
            "gas": 200000,
        })
        receipt = send_tx(withdraw_tx)
        new_bal = vault.functions.balanceOf(address).call()

        output({
            "success": True,
            "action": "withdraw",
            "amount": args.amount,
            "txHash": receipt.transactionHash.hex(),
            "newBalance": round(new_bal / 10 ** USDC_DECIMALS, 6),
        })

    # ---- Mint shares (Exchange contract) ----
    elif args.action == "mint":
        if args.market_id is None:
            error_exit("--market-id is required for mint")
        if args.amount is None or args.amount <= 0:
            error_exit("--amount is required and must be positive for mint")

        amount_raw = int(args.amount * 10 ** USDC_DECIMALS)

        mint_tx = exchange.functions.mintShares(args.market_id, amount_raw).build_transaction({
            "from": address,
            "nonce": w3.eth.get_transaction_count(address),
            "gas": 200000,
        })
        receipt = send_tx(mint_tx)

        # Read back share balances
        yes = exchange.functions.yesShares(args.market_id, address).call()
        no = exchange.functions.noShares(args.market_id, address).call()

        output({
            "success": True,
            "action": "mint",
            "marketId": args.market_id,
            "amountMinted": args.amount,
            "txHash": receipt.transactionHash.hex(),
            "yesShares": round(yes / 10 ** USDC_DECIMALS, 6),
            "noShares": round(no / 10 ** USDC_DECIMALS, 6),
        })

    # ---- Merge shares (Exchange contract) ----
    elif args.action == "merge":
        if args.market_id is None:
            error_exit("--market-id is required for merge")
        if args.amount is None or args.amount <= 0:
            error_exit("--amount is required and must be positive for merge")

        amount_raw = int(args.amount * 10 ** USDC_DECIMALS)

        merge_tx = exchange.functions.mergeShares(args.market_id, amount_raw).build_transaction({
            "from": address,
            "nonce": w3.eth.get_transaction_count(address),
            "gas": 200000,
        })
        receipt = send_tx(merge_tx)

        # Read back balances
        yes = exchange.functions.yesShares(args.market_id, address).call()
        no = exchange.functions.noShares(args.market_id, address).call()
        vault_bal = vault.functions.balanceOf(address).call()

        output({
            "success": True,
            "action": "merge",
            "marketId": args.market_id,
            "amountMerged": args.amount,
            "txHash": receipt.transactionHash.hex(),
            "remainingYesShares": round(yes / 10 ** USDC_DECIMALS, 6),
            "remainingNoShares": round(no / 10 ** USDC_DECIMALS, 6),
            "vaultBalance": round(vault_bal / 10 ** USDC_DECIMALS, 6),
        })

    # ---- Claim winnings (Exchange contract) ----
    elif args.action == "claim":
        if args.market_id is None:
            error_exit("--market-id is required for claim")

        # Check shares first
        yes = exchange.functions.yesShares(args.market_id, address).call()
        no = exchange.functions.noShares(args.market_id, address).call()

        if yes == 0 and no == 0:
            output({
                "success": True,
                "action": "claim",
                "marketId": args.market_id,
                "message": "No shares to claim",
                "yesShares": 0,
                "noShares": 0,
            })
            return

        claim_tx = exchange.functions.claimWinnings(args.market_id).build_transaction({
            "from": address,
            "nonce": w3.eth.get_transaction_count(address),
            "gas": 200000,
        })
        receipt = send_tx(claim_tx)
        vault_bal = vault.functions.balanceOf(address).call()

        output({
            "success": True,
            "action": "claim",
            "marketId": args.market_id,
            "txHash": receipt.transactionHash.hex(),
            "claimedYesShares": round(yes / 10 ** USDC_DECIMALS, 6),
            "claimedNoShares": round(no / 10 ** USDC_DECIMALS, 6),
            "newVaultBalance": round(vault_bal / 10 ** USDC_DECIMALS, 6),
        })


if __name__ == "__main__":
    main()
