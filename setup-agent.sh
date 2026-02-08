#!/bin/bash
#
# Setup a single agent wallet for trading on Blackjack Markets.
#
# What this does:
#   1. Generates a fresh wallet (private key)
#   2. Creates a config file (agent.env or custom name)
#   3. Prints instructions for funding MON (gas) and USDC
#
# With --fund flag:
#   Approves and deposits USDC into the Vault for an existing agent
#
# Prerequisites:
#   - cast (foundry) installed: curl -L https://foundry.paradigm.xyz | bash && foundryup
#   - pip install -r requirements.txt
#   - Exchange service running on EXCHANGE_URL
#   - Game server running (so markets exist to trade)
#
# Usage:
#   # Generate wallet and env file
#   bash setup-agent.sh                     # creates agent.env with defaults
#   bash setup-agent.sh --interactive       # choose personality, risk, name
#   bash setup-agent.sh agent-1             # creates agent-1.env
#
#   # Fund MON + USDC (see printed instructions), then:
#   bash setup-agent.sh --fund              # deposits from agent.env
#   bash setup-agent.sh --fund agent-1      # deposits from agent-1.env

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# ── Activate venv if present ─────────────────────────────────

if [ -d "venv" ] && [ -f "venv/bin/activate" ]; then
    source venv/bin/activate
fi

# ── Source existing agent.env for defaults ────────────────────
# Parse arguments first to determine which env file to source

_AGENT_NAME="agent"
for _arg in "$@"; do
    if [[ "$_arg" != -* ]] && [ "$_arg" != "--fund" ]; then
        _AGENT_NAME="$_arg"
    fi
done
_ENV_FILE="${_AGENT_NAME}.env"

if [ -f "$_ENV_FILE" ]; then
    set -a && source "$_ENV_FILE" && set +a
fi

# ── Network presets ───────────────────────────────────────────
# Set NETWORK=mainnet to switch (default: testnet)

NETWORK="${NETWORK:-testnet}"

if [ "$NETWORK" = "mainnet" ]; then
    RPC_URL="${RPC_URL:-https://rpc.monad.xyz}"
    CHAIN_ID="${CHAIN_ID:-143}"
    # Update these after mainnet deployment
    USDC_ADDRESS="${USDC_ADDRESS:-0xDE6498947808BCcD50F18785Cc3B0C472380C1fB}"
    VAULT_ADDRESS="${VAULT_ADDRESS:-0xd1a710199b84899856696Ce0AA30377fB7B485C3}"
    EXCHANGE_ADDRESS="${EXCHANGE_ADDRESS:-0xC628e81B506b572391669339c2AbaCFafa0d95dD}"
else
    RPC_URL="${RPC_URL:-https://testnet-rpc.monad.xyz}"
    CHAIN_ID="${CHAIN_ID:-10143}"
    USDC_ADDRESS="${USDC_ADDRESS:-0xDE6498947808BCcD50F18785Cc3B0C472380C1fB}"
    VAULT_ADDRESS="${VAULT_ADDRESS:-0xd1a710199b84899856696Ce0AA30377fB7B485C3}"
    EXCHANGE_ADDRESS="${EXCHANGE_ADDRESS:-0xC628e81B506b572391669339c2AbaCFafa0d95dD}"
fi

EXCHANGE_URL="${EXCHANGE_URL:-http://localhost:3002}"
EXCHANGE_WS_URL="${EXCHANGE_WS_URL:-ws://localhost:3002}"

DEPOSIT_AMOUNT="${DEPOSIT_AMOUNT:-all}"   # USDC to deposit ("all" = entire balance)

# Moltbook MON faucet (Monad Foundation — mainnet MON)
MOLTBOOK_FAUCET_URL="https://www.moltbook.com/post/74fcca14-4208-48cf-9808-25dcb1036e63"

# ── Parse arguments ───────────────────────────────────────────

FUND_MODE=false
INTERACTIVE=false
AGENT_NAME="agent"

for arg in "$@"; do
    if [ "$arg" = "--fund" ]; then
        FUND_MODE=true
    elif [ "$arg" = "--interactive" ] || [ "$arg" = "-i" ]; then
        INTERACTIVE=true
    elif [[ "$arg" != -* ]]; then
        AGENT_NAME="$arg"
    fi
done

ENV_FILE="${AGENT_NAME}.env"

# ── Preflight checks ─────────────────────────────────────────

if ! command -v cast &> /dev/null; then
    echo "ERROR: 'cast' not found. Install Foundry:"
    echo "  curl -L https://foundry.paradigm.xyz | bash && foundryup"
    exit 1
fi

# ── Fund mode: approve + deposit for existing wallet ──────────

if [ "$FUND_MODE" = true ]; then
    if [ ! -f "$ENV_FILE" ]; then
        echo "ERROR: $ENV_FILE not found. Run setup-agent.sh ${AGENT_NAME} first."
        exit 1
    fi

    PRIVATE_KEY=$(grep "^PRIVATE_KEY=" "$ENV_FILE" | cut -d= -f2)
    ADDRESS=$(cast wallet address "$PRIVATE_KEY" 2>/dev/null)

    echo "============================================"
    echo "  Funding: $AGENT_NAME ($ADDRESS)"
    echo "============================================"
    echo ""
    echo "Network:  $NETWORK"
    echo "Chain ID: $CHAIN_ID"
    echo "RPC:      $RPC_URL"
    echo ""

    # Validate chain ID matches RPC
    ACTUAL_CHAIN=$(cast chain-id --rpc-url "$RPC_URL" 2>/dev/null || echo "")
    if [ -n "$ACTUAL_CHAIN" ] && [ "$ACTUAL_CHAIN" != "$CHAIN_ID" ]; then
        echo "ERROR: Chain ID mismatch. RPC reports $ACTUAL_CHAIN, config expects $CHAIN_ID."
        echo "Check RPC_URL and CHAIN_ID in $ENV_FILE."
        exit 1
    fi

    # Check MON balance
    MON_WEI=$(cast balance "$ADDRESS" --rpc-url "$RPC_URL" 2>/dev/null || echo "0")
    if [ "$MON_WEI" = "0" ]; then
        echo "ERROR: No MON balance. Agent needs gas to transact."
        echo "See funding instructions from the initial setup."
        exit 1
    fi
    echo "MON balance: $(cast from-wei "$MON_WEI" 2>/dev/null || echo "$MON_WEI wei")"

    # Check USDC balance
    USDC_BAL=$(cast call "$USDC_ADDRESS" "balanceOf(address)(uint256)" "$ADDRESS" --rpc-url "$RPC_URL" 2>/dev/null || echo "0")
    USDC_HUMAN=$(echo "scale=2; $USDC_BAL / 1000000" | bc 2>/dev/null || echo "?")
    echo "USDC balance: $USDC_HUMAN"

    if [ "$USDC_BAL" = "0" ] || [ "$USDC_BAL" = "" ]; then
        echo "ERROR: No USDC balance. Send USDC to $ADDRESS first."
        exit 1
    fi

    # Determine deposit amount ("all" = entire balance, or specific USDC amount)
    if [ "$DEPOSIT_AMOUNT" = "all" ]; then
        ACTUAL_DEPOSIT="$USDC_BAL"
        ACTUAL_HUMAN="$USDC_HUMAN"
        echo "Depositing all: $USDC_HUMAN USDC"
    else
        DEPOSIT_RAW=$(echo "$DEPOSIT_AMOUNT * 1000000" | bc 2>/dev/null || echo "$((DEPOSIT_AMOUNT * 1000000))")
        if [ "$USDC_BAL" -lt "$DEPOSIT_RAW" ] 2>/dev/null; then
            ACTUAL_DEPOSIT="$USDC_BAL"
            ACTUAL_HUMAN="$USDC_HUMAN"
            echo "NOTE: Only $USDC_HUMAN USDC available (requested $DEPOSIT_AMOUNT), depositing all"
        else
            ACTUAL_DEPOSIT="$DEPOSIT_RAW"
            ACTUAL_HUMAN="$DEPOSIT_AMOUNT"
        fi
    fi

    # Approve vault
    echo "Approving Vault..."
    cast send "$USDC_ADDRESS" \
        "approve(address,uint256)" \
        "$VAULT_ADDRESS" \
        "115792089237316195423570985008687907853269984665640564039457584007913129639935" \
        --rpc-url "$RPC_URL" \
        --private-key "$PRIVATE_KEY" \
        --quiet 2>/dev/null && echo "Approved." || {
            echo "ERROR: Approval failed."
            exit 1
        }

    # Deposit
    echo "Depositing $ACTUAL_HUMAN USDC into Vault..."
    cast send "$VAULT_ADDRESS" \
        "deposit(uint256)" \
        "$ACTUAL_DEPOSIT" \
        --rpc-url "$RPC_URL" \
        --private-key "$PRIVATE_KEY" \
        --quiet 2>/dev/null && echo "Deposited." || {
            echo "ERROR: Deposit failed."
            exit 1
        }

    # Verify
    VAULT_BAL=$(cast call "$VAULT_ADDRESS" "balanceOf(address)(uint256)" "$ADDRESS" --rpc-url "$RPC_URL" 2>/dev/null || echo "0")
    VAULT_HUMAN=$(echo "scale=2; $VAULT_BAL / 1000000" | bc 2>/dev/null || echo "?")
    echo "Vault balance: $VAULT_HUMAN USDC"
    echo ""

    # Run ready check for immediate feedback
    echo "============================================"
    echo "  Ready Check"
    echo "============================================"
    # Source the agent env so ready_check picks it up
    set -a && source "$ENV_FILE" && set +a
    python3 tools/ready_check.py 2>&1 >/dev/null || true
    echo ""
    exit 0
fi

# ── Main setup: generate wallet ──────────────────────────────

if [ -f "$ENV_FILE" ]; then
    echo "WARNING: $ENV_FILE already exists."
    echo "To avoid overwriting an existing wallet, choose a different name:"
    echo "  bash setup-agent.sh agent-2"
    echo ""
    echo "Or delete the file first if you're sure:"
    echo "  rm $ENV_FILE && bash setup-agent.sh $AGENT_NAME"
    exit 1
fi

echo "============================================"
echo "  Blackjack Trader — Agent Setup"
echo "============================================"
echo ""
echo "Chain:    $CHAIN_ID"
echo "RPC:      $RPC_URL"
echo "Exchange: $EXCHANGE_URL"
echo ""

# Generate wallet
WALLET_OUTPUT=$(cast wallet new 2>&1)
PRIVATE_KEY=$(echo "$WALLET_OUTPUT" | grep "Private key:" | awk '{print $3}')
ADDRESS=$(echo "$WALLET_OUTPUT" | grep "Address:" | awk '{print $2}')

echo "Address:     $ADDRESS"
echo "Private key: ${PRIVATE_KEY:0:10}...${PRIVATE_KEY: -4}"
echo ""

# ── Agent personality (interactive or defaults) ────────────

# Defaults
BOT_NAME="$AGENT_NAME"
STRATEGY="all"
AGGRESSIVENESS="moderate"
PROFIT_GOAL="make \$25 today"
PROFIT_MODE="compound"
MAX_POSITION_USDC=50
DEFAULT_ORDER_SIZE_USDC=5
MAX_EXPOSURE_PCT=70
STOP_LOSS_PCT=20

if [ "$INTERACTIVE" = true ]; then
    echo "============================================"
    echo "  Agent Personality"
    echo "============================================"
    echo ""

    # Name
    read -rp "Agent name? (default: $BOT_NAME): " _name
    [ -n "$_name" ] && BOT_NAME="$_name"
    echo ""

    # Trading style
    echo "What kind of trader should this be?"
    echo "  1) Conservative Value Investor (patient, high-conviction bets only)"
    echo "  2) Aggressive Market Maker (fast, frequent trades, capture spreads)"
    echo "  3) Momentum Trader (follow trends, buy into strength)"
    echo "  4) Balanced All-Rounder (mix of everything — default)"
    echo "  5) Custom (configure manually)"
    echo ""
    read -rp "Choice [1-5] (default: 4): " _style
    case "$_style" in
        1)
            STRATEGY="value"
            AGGRESSIVENESS="conservative"
            ;;
        2)
            STRATEGY="market_making,arbitrage"
            AGGRESSIVENESS="aggressive"
            ;;
        3)
            STRATEGY="momentum,value"
            AGGRESSIVENESS="aggressive"
            ;;
        4|"")
            STRATEGY="all"
            AGGRESSIVENESS="moderate"
            ;;
        5)
            read -rp "  Strategies (value,market_making,arbitrage,momentum,all): " _strat
            [ -n "$_strat" ] && STRATEGY="$_strat"
            read -rp "  Aggressiveness (conservative/moderate/aggressive/yolo): " _agg
            [ -n "$_agg" ] && AGGRESSIVENESS="$_agg"
            ;;
    esac
    echo ""

    # Risk tolerance
    echo "Risk tolerance?"
    echo "  1) Low    — max \$10/trade, 30% of balance deployed"
    echo "  2) Medium — max \$25/trade, 50% of balance deployed"
    echo "  3) High   — max \$50/trade, 70% of balance deployed (default)"
    echo "  4) YOLO   — max \$100/trade, 90% of balance deployed"
    echo ""
    read -rp "Choice [1-4] (default: 3): " _risk
    case "$_risk" in
        1)
            MAX_POSITION_USDC=10
            DEFAULT_ORDER_SIZE_USDC=2
            MAX_EXPOSURE_PCT=30
            STOP_LOSS_PCT=10
            ;;
        2)
            MAX_POSITION_USDC=25
            DEFAULT_ORDER_SIZE_USDC=5
            MAX_EXPOSURE_PCT=50
            STOP_LOSS_PCT=15
            ;;
        3|"")
            MAX_POSITION_USDC=50
            DEFAULT_ORDER_SIZE_USDC=5
            MAX_EXPOSURE_PCT=70
            STOP_LOSS_PCT=20
            ;;
        4)
            MAX_POSITION_USDC=100
            DEFAULT_ORDER_SIZE_USDC=10
            MAX_EXPOSURE_PCT=90
            STOP_LOSS_PCT=30
            [ "$AGGRESSIVENESS" != "yolo" ] && AGGRESSIVENESS="aggressive"
            ;;
    esac
    echo ""

    # Profit goal
    read -rp "Profit goal? (default: make \$25 today): " _goal
    [ -n "$_goal" ] && PROFIT_GOAL="$_goal"

    # Profit mode
    echo ""
    echo "What should the agent do with profits?"
    echo "  1) Compound — reinvest everything, keep growing (default)"
    echo "  2) Cashout  — take profits and send to your personal wallet"
    echo ""
    read -rp "Choice [1-2] (default: 1): " _mode
    case "$_mode" in
        2) PROFIT_MODE="cashout" ;;
        *) PROFIT_MODE="compound" ;;
    esac
    echo ""

    echo "============================================"
    echo "  $BOT_NAME — $STRATEGY / $AGGRESSIVENESS"
    echo "  Goal: $PROFIT_GOAL"
    echo "  Risk: max \$$MAX_POSITION_USDC/trade, ${MAX_EXPOSURE_PCT}% exposure"
    echo "  Profits: $PROFIT_MODE"
    echo "============================================"
    echo ""
fi

# Write env file
cat > "$ENV_FILE" << EOF
# $BOT_NAME — $ADDRESS
# Network: $NETWORK (change to "mainnet" when ready)
AGENT_NAME=$BOT_NAME
NETWORK=$NETWORK
PRIVATE_KEY=$PRIVATE_KEY
EXCHANGE_URL=$EXCHANGE_URL
EXCHANGE_WS_URL=$EXCHANGE_WS_URL
CHAIN_ID=$CHAIN_ID
EXCHANGE_ADDRESS=$EXCHANGE_ADDRESS
VAULT_ADDRESS=$VAULT_ADDRESS
USDC_ADDRESS=$USDC_ADDRESS
RPC_URL=$RPC_URL
# ── Trading personality ──────────────────────────────────
# STRATEGY: comma-separated list of strategies to use
#   Options: value, market_making, arbitrage, momentum, all
STRATEGY=$STRATEGY
# AGGRESSIVENESS: how much risk to take
#   Options: conservative, moderate, aggressive, yolo
AGGRESSIVENESS=$AGGRESSIVENESS
# PROFIT_GOAL: natural language target for the session
#   Examples: "make \$20 today", "double my money", "slow and steady 5% gains"
PROFIT_GOAL=$PROFIT_GOAL
# PROFIT_MODE: what to do with profits
#   compound = reinvest everything, keep growing the balance
#   cashout  = when ahead of target, transfer profits to WITHDRAW_TO
PROFIT_MODE=$PROFIT_MODE

# ── Risk limits ─────────────────────────────────────────
MAX_POSITION_USDC=$MAX_POSITION_USDC
DEFAULT_ORDER_SIZE_USDC=$DEFAULT_ORDER_SIZE_USDC
MAX_EXPOSURE_PCT=$MAX_EXPOSURE_PCT
STOP_LOSS_PCT=$STOP_LOSS_PCT

# ── Cashout ─────────────────────────────────────────────
# Set this to your personal wallet address to enable cashout
# WITHDRAW_TO=0xYourPersonalWalletAddress
EOF
echo "Config written to $ENV_FILE"
echo ""

# ── Funding instructions ─────────────────────────────────────

echo "============================================"
echo "  Step 1: Fund MON (gas token)"
echo "============================================"
echo ""
echo "The agent needs MON to pay for on-chain transactions"
echo "(vault deposits, share minting, etc)."
echo ""
echo "OPTION A — Moltbook Faucet (50 MON, recommended)"
echo ""
echo "  The Monad Foundation is distributing 50 MON to agents via Moltbook."
echo "  Post this address in the faucet thread:"
echo ""
echo "    $MOLTBOOK_FAUCET_URL"
echo ""
echo "    Address: $ADDRESS"
echo ""
echo "  Requirements:"
echo "    - Fresh address (never used before)"
echo "    - Not an exchange deposit address"
echo "    - Moltbook account required to post"
echo ""
echo "  If the faucet is dry or the promotion has ended, use Option B."
echo ""
echo "OPTION B — Transfer from your own wallet"
echo ""
echo "  cast send $ADDRESS --value 1ether --rpc-url $RPC_URL --private-key YOUR_KEY"
echo ""

echo "============================================"
echo "  Step 2: Fund USDC"
echo "============================================"
echo ""
echo "Send USDC to the agent from your own wallet:"
echo ""
echo "  cast send $USDC_ADDRESS \"transfer(address,uint256)\" $ADDRESS 500000000 --rpc-url $RPC_URL --private-key YOUR_KEY"
echo ""
echo "(500000000 = 500 USDC. Adjust as needed.)"
echo ""

echo "============================================"
echo "  Step 3: Deposit USDC into Vault"
echo "============================================"
echo ""
echo "Once the agent has MON and USDC:"
echo ""
echo "  bash setup-agent.sh --fund $AGENT_NAME"
echo ""

echo "============================================"
echo "  Launch"
echo "============================================"
echo ""
echo "  cd $(pwd)"
echo "  set -a && source $ENV_FILE && set +a"
echo "  python3 tools/fetch_state.py"
echo ""
echo "Or via OpenClaw:"
echo ""
echo "  PRIVATE_KEY=\$(grep PRIVATE_KEY $(pwd)/$ENV_FILE | cut -d= -f2) /blackjack-trader scan for opportunities"
echo ""
