#!/bin/bash
#
# One-command installer for blackjack-trader.
#
# What this does:
#   1. Checks Python 3.10+ is available
#   2. Creates a virtual environment
#   3. Installs Python dependencies
#   4. Checks Foundry (cast) is installed
#   5. Generates an agent wallet
#   6. Runs ready check
#
# Usage:
#   bash install.sh                    # testnet (default)
#   NETWORK=mainnet bash install.sh    # mainnet
#
# After install, fund MON + USDC to the printed address, then:
#   bash setup-agent.sh --fund

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo "============================================"
echo "  Blackjack Trader — Install"
echo "============================================"
echo ""

# ── Step 1: Python ────────────────────────────────────────────

PYTHON=""
for cmd in python3 python; do
    if command -v "$cmd" &>/dev/null; then
        version=$("$cmd" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null)
        major=$("$cmd" -c "import sys; print(sys.version_info.major)" 2>/dev/null)
        minor=$("$cmd" -c "import sys; print(sys.version_info.minor)" 2>/dev/null)
        if [ "$major" = "3" ] && [ "$minor" -ge "10" ]; then
            PYTHON="$cmd"
            break
        fi
    fi
done

if [ -z "$PYTHON" ]; then
    echo "ERROR: Python 3.10+ not found."
    echo "  Install: https://www.python.org/downloads/"
    exit 1
fi
echo "[1/5] Python $version ✓"

# ── Step 2: Virtual environment ───────────────────────────────

if [ ! -d "venv" ]; then
    "$PYTHON" -m venv venv
    echo "[2/5] Virtual environment created ✓"
else
    echo "[2/5] Virtual environment exists ✓"
fi

# Activate
source venv/bin/activate

# ── Step 3: Dependencies ─────────────────────────────────────

pip install -q -r requirements.txt
echo "[3/5] Dependencies installed ✓"

# ── Step 4: Foundry ──────────────────────────────────────────

if command -v cast &>/dev/null; then
    echo "[4/5] Foundry (cast) ✓"
else
    echo "[4/5] Foundry not found — installing..."
    curl -sSL https://foundry.paradigm.xyz | bash 2>/dev/null
    export PATH="$HOME/.foundry/bin:$PATH"
    foundryup -q 2>/dev/null || true
    if command -v cast &>/dev/null; then
        echo "      Foundry installed ✓"
    else
        echo "      WARNING: Foundry install failed. Install manually:"
        echo "        curl -L https://foundry.paradigm.xyz | bash && foundryup"
        echo "      (Continuing — wallet generation requires cast)"
    fi
fi

# ── Step 5: Generate wallet ──────────────────────────────────

if [ -f "agent.env" ]; then
    echo "[5/5] Wallet exists (agent.env) ✓"
else
    bash setup-agent.sh
    echo "[5/5] Wallet generated ✓"
fi

# ── Ready check ──────────────────────────────────────────────

echo ""
echo "============================================"
echo "  Ready Check"
echo "============================================"
python3 tools/ready_check.py 2>&1 >/dev/null || true

echo ""
echo "============================================"
echo "  Next Steps"
echo "============================================"
echo ""
echo "1. Fund MON (gas) + USDC to the agent address above"
echo "2. bash setup-agent.sh --fund"
echo "3. Start trading: /blackjack-trader scan for opportunities"
echo ""
