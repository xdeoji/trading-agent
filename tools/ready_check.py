#!/usr/bin/env python3
"""Pre-flight validation — checks that the agent is configured, funded, and connected.

Outputs JSON with PASS/FAIL per check and a final summary.
"""

import json
import os
import sys

USDC_DECIMALS = 6


def check_deps():
    """Verify required Python packages are importable."""
    missing = []
    for pkg in ["eth_account", "web3", "requests", "websockets"]:
        try:
            __import__(pkg)
        except ImportError:
            missing.append(pkg)
    if missing:
        return "FAIL", f"Missing packages: {', '.join(missing)}. Run: pip install -r requirements.txt"
    return "PASS", None


def check_config(cfg):
    """Verify PRIVATE_KEY is set and derivable to an address."""
    pk = cfg.get("PRIVATE_KEY", "")
    if not pk:
        return "FAIL", "PRIVATE_KEY not set. Run setup-agent.sh or export PRIVATE_KEY", None
    try:
        from eth_account import Account
        address = Account.from_key(pk).address
        return "PASS", None, address
    except Exception as e:
        return "FAIL", f"Cannot derive address from PRIVATE_KEY: {e}", None


def check_network(cfg):
    """Verify the Exchange API is reachable."""
    import requests
    url = f"{cfg['EXCHANGE_URL']}/api/markets"
    try:
        r = requests.get(url, timeout=5)
        if r.status_code == 200:
            return "PASS", None
        return "FAIL", f"Exchange returned HTTP {r.status_code}"
    except requests.ConnectionError:
        return "FAIL", f"Cannot connect to exchange at {cfg['EXCHANGE_URL']}"
    except requests.Timeout:
        return "FAIL", f"Exchange timed out at {url}"
    except Exception as e:
        return "FAIL", f"Exchange check failed: {e}"


def check_rpc(cfg):
    """Verify Monad RPC responds and chain ID matches."""
    from web3 import Web3
    w3 = Web3(Web3.HTTPProvider(cfg["RPC_URL"]))
    try:
        chain_id = w3.eth.chain_id
        expected = cfg["CHAIN_ID"]
        if chain_id != expected:
            return "FAIL", f"Chain ID mismatch: got {chain_id}, expected {expected}"
        return "PASS", None
    except Exception as e:
        return "FAIL", f"Cannot connect to RPC at {cfg['RPC_URL']}: {e}"


def check_mon(cfg, address):
    """Verify address has MON for gas."""
    from web3 import Web3
    w3 = Web3(Web3.HTTPProvider(cfg["RPC_URL"]))
    try:
        balance = w3.eth.get_balance(address)
        if balance > 0:
            mon = balance / 10**18
            return "PASS", None, mon
        return "FAIL", "No MON balance — agent needs gas to transact", 0
    except Exception as e:
        return "FAIL", f"Cannot check MON balance: {e}", 0


def check_vault(cfg, address):
    """Verify address has USDC in vault or wallet."""
    from web3 import Web3

    ERC20_BALANCE_ABI = [{
        "inputs": [{"name": "account", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    }]

    w3 = Web3(Web3.HTTPProvider(cfg["RPC_URL"]))
    vault_addr = Web3.to_checksum_address(cfg["VAULT_ADDRESS"])
    usdc_addr = Web3.to_checksum_address(cfg["USDC_ADDRESS"])
    address = Web3.to_checksum_address(address)

    try:
        vault = w3.eth.contract(address=vault_addr, abi=ERC20_BALANCE_ABI)
        usdc = w3.eth.contract(address=usdc_addr, abi=ERC20_BALANCE_ABI)
        vault_bal = vault.functions.balanceOf(address).call()
        wallet_bal = usdc.functions.balanceOf(address).call()
        vault_usdc = vault_bal / 10**USDC_DECIMALS
        wallet_usdc = wallet_bal / 10**USDC_DECIMALS

        if vault_bal > 0 or wallet_bal > 0:
            return "PASS", None, vault_usdc, wallet_usdc
        return "FAIL", "No USDC in vault or wallet", 0, 0
    except Exception as e:
        return "FAIL", f"Cannot check balances: {e}", 0, 0


def main():
    # Load config (uses auto-discovery of agent.env)
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from _config import load_config
    cfg = load_config()

    checks = {}
    failures = []
    address = None
    details = {}

    # 1. Dependencies
    status, err = check_deps()
    checks["deps"] = status
    if err:
        failures.append(("DEPS", err))

    # 2. Config / PRIVATE_KEY
    if checks.get("deps") == "PASS":
        status, err, addr = check_config(cfg)
        checks["config"] = status
        if err:
            failures.append(("CONFIG", err))
        else:
            address = addr
            details["address"] = addr
    else:
        checks["config"] = "SKIP"

    # 3. Network (Exchange API) — independent of config
    if checks.get("deps") == "PASS":
        status, err = check_network(cfg)
        checks["network"] = status
        if err:
            failures.append(("NETWORK", err))
    else:
        checks["network"] = "SKIP"

    # 4. RPC
    if checks.get("deps") == "PASS":
        status, err = check_rpc(cfg)
        checks["rpc"] = status
        if err:
            failures.append(("RPC", err))
    else:
        checks["rpc"] = "SKIP"

    # 5. MON balance (needs address + RPC)
    if address and checks.get("rpc") == "PASS":
        status, err, mon = check_mon(cfg, address)
        checks["mon"] = status
        if err:
            failures.append(("MON", err))
        details["monBalance"] = round(mon, 4)
    else:
        checks["mon"] = "SKIP"

    # 6. Vault/USDC balance
    if address and checks.get("rpc") == "PASS":
        status, err, vault_bal, wallet_bal = check_vault(cfg, address)
        checks["vault"] = status
        if err:
            failures.append(("VAULT", err))
        details["vaultUSDC"] = round(vault_bal, 2)
        details["walletUSDC"] = round(wallet_bal, 2)
    else:
        checks["vault"] = "SKIP"

    # Summary
    success = len(failures) == 0
    if success:
        summary = "GREEN LIGHT — ready to trade"
    else:
        labels = [f[0] for f in failures]
        summary = f"{len(failures)} check(s) failed: {', '.join(labels)}"

    result = {
        "success": success,
        "checks": checks,
        "summary": summary,
        **details,
    }

    # Print human-readable version to stderr, JSON to stdout
    print("", file=sys.stderr)
    for name, status in checks.items():
        icon = "+" if status == "PASS" else ("-" if status == "FAIL" else "?")
        print(f"  [{icon}] {name.upper():8s} {status}", file=sys.stderr)
    print("", file=sys.stderr)
    if failures:
        for label, msg in failures:
            print(f"  {label}: {msg}", file=sys.stderr)
        print("", file=sys.stderr)
    if address:
        print(f"  Address: {address}", file=sys.stderr)
    print(f"  {summary}", file=sys.stderr)
    print("", file=sys.stderr)

    json.dump(result, sys.stdout, default=str)
    print()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
