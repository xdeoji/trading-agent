"""Shared configuration loader for all tools."""

import glob
import json
import os
import sys

# Resolve paths relative to this file's parent directory (the skill root)
_SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_CONFIG_PATH = os.path.join(_SKILL_DIR, "config.json")

# Network presets — switch with NETWORK=mainnet or NETWORK=testnet
_NETWORKS = {
    "testnet": {
        "CHAIN_ID": "10143",
        "RPC_URL": "https://testnet-rpc.monad.xyz",
        "EXCHANGE_ADDRESS": "0xC628e81B506b572391669339c2AbaCFafa0d95dD",
        "VAULT_ADDRESS": "0xd1a710199b84899856696Ce0AA30377fB7B485C3",
        "USDC_ADDRESS": "0xDE6498947808BCcD50F18785Cc3B0C472380C1fB",
    },
    "mainnet": {
        "CHAIN_ID": "143",
        "RPC_URL": "https://rpc.monad.xyz",
        # Update these after mainnet deployment
        "EXCHANGE_ADDRESS": "0xC628e81B506b572391669339c2AbaCFafa0d95dD",
        "VAULT_ADDRESS": "0xd1a710199b84899856696Ce0AA30377fB7B485C3",
        "USDC_ADDRESS": "0xDE6498947808BCcD50F18785Cc3B0C472380C1fB",
    },
}
_DEFAULT_NETWORK = "testnet"


def _parse_env_file(path: str) -> dict:
    """Parse a .env file into a dict. Skips comments and blank lines."""
    env = {}
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            key, _, value = line.partition("=")
            env[key.strip()] = value.strip()
    return env


def _load_agent_env() -> dict:
    """Auto-discover agent*.env in the skill root directory."""
    env_files = sorted(glob.glob(os.path.join(_SKILL_DIR, "agent*.env")))
    if env_files:
        return _parse_env_file(env_files[0])
    return {}


def _fetch_exchange_config(exchange_url: str) -> dict:
    """Fetch contract addresses and network config from the exchange service."""
    try:
        import requests
        r = requests.get(f"{exchange_url}/api/config", timeout=3)
        if r.status_code == 200:
            data = r.json()
            result = {}
            if data.get("chainId"):
                result["CHAIN_ID"] = str(data["chainId"])
            if data.get("rpcUrl"):
                result["RPC_URL"] = data["rpcUrl"]
            if data.get("network"):
                result["NETWORK"] = data["network"]
            contracts = data.get("contracts", {})
            if contracts.get("exchange"):
                result["EXCHANGE_ADDRESS"] = contracts["exchange"]
            if contracts.get("vault"):
                result["VAULT_ADDRESS"] = contracts["vault"]
            if contracts.get("usdc"):
                result["USDC_ADDRESS"] = contracts["usdc"]
            return result
    except Exception:
        pass
    return {}


def load_config() -> dict:
    """Load config with priority: env vars > agent.env > config.json > exchange API > network preset."""
    # Lowest priority: network preset
    network = os.environ.get("NETWORK", _DEFAULT_NETWORK)
    preset = _NETWORKS.get(network, _NETWORKS[_DEFAULT_NETWORK])

    # Next: config.json
    file_config = {}
    if os.path.exists(_CONFIG_PATH):
        with open(_CONFIG_PATH) as f:
            file_config = json.load(f)

    # Next: agent.env (agent-specific runtime config)
    agent_env = _load_agent_env()

    # Resolve EXCHANGE_URL early (needed for API config fetch)
    exchange_url = os.environ.get(
        "EXCHANGE_URL",
        agent_env.get("EXCHANGE_URL", file_config.get("EXCHANGE_URL", "http://localhost:3002"))
    )

    # Fetch live config from exchange (between config.json and agent.env in priority)
    remote_config = _fetch_exchange_config(exchange_url)

    def get(key: str, default: str = "") -> str:
        return os.environ.get(key, agent_env.get(key, file_config.get(key, remote_config.get(key, preset.get(key, default)))))

    return {
        "PRIVATE_KEY": get("PRIVATE_KEY"),
        "EXCHANGE_URL": exchange_url,
        "EXCHANGE_WS_URL": get("EXCHANGE_WS_URL", "ws://localhost:3002"),
        "CHAIN_ID": int(get("CHAIN_ID")),
        "EXCHANGE_ADDRESS": get("EXCHANGE_ADDRESS"),
        "VAULT_ADDRESS": get("VAULT_ADDRESS"),
        "USDC_ADDRESS": get("USDC_ADDRESS"),
        "RPC_URL": get("RPC_URL"),
        "NETWORK": get("NETWORK", network),
        "MAX_POSITION_USDC": float(get("MAX_POSITION_USDC", "50")),
        "DEFAULT_ORDER_SIZE_USDC": float(get("DEFAULT_ORDER_SIZE_USDC", "5")),
        "PNL_TARGET_DAILY": float(get("PNL_TARGET_DAILY", "25")),
        "MAX_EXPOSURE_PCT": float(get("MAX_EXPOSURE_PCT", "70")),
        "STOP_LOSS_PCT": float(get("STOP_LOSS_PCT", "20")),
    }


def get_address_from_key(private_key: str) -> str:
    """Derive address from private key using eth_account."""
    from eth_account import Account
    return Account.from_key(private_key).address


def require_private_key(cfg: dict) -> str:
    """Ensure PRIVATE_KEY is set, exit with error JSON if not."""
    pk = cfg["PRIVATE_KEY"]
    if not pk:
        json.dump({"success": False, "error": "PRIVATE_KEY not set. Export it or add to config.json"}, sys.stdout)
        print()
        sys.exit(1)
    return pk


def output(data: dict) -> None:
    """Print JSON output to stdout."""
    json.dump(data, sys.stdout, default=str)
    print()


def error_exit(msg: str) -> None:
    """Print error JSON and exit with code 1."""
    output({"success": False, "error": msg})
    sys.exit(1)
