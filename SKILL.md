---
name: blackjack-trader
description: "Autonomous profit-seeking AI agent for blackjack prediction markets on Monad. Trades directionally, provides liquidity, arbitrages mispricings, and manages risk — all to hit a daily P&L target."
user-invocable: true
command-dispatch: tool
command-tool: Bash
command-arg-mode: raw
metadata: {"openclaw": {"emoji": "🃏", "requires": {"bins": ["python3", "pip"], "env": ["PRIVATE_KEY", "EXCHANGE_URL"]}, "primaryEnv": "PRIVATE_KEY"}}
---

# Blackjack Trader

Autonomous trading agent for Blackjack Markets. You find and capture profit from prediction markets on blackjack hand outcomes — through any strategy that works.

**Read AGENTS.md for how to think. This file is what you can do.**

## Tools

All tools live in `tools/` relative to this skill. Run them via Bash. All output JSON to stdout.

```bash
python3 ./tools/fetch_state.py                  # Full state: balance, markets, positions, orders
python3 ./tools/market_analysis.py              # Edge signals: arb, spread, depth, volume
python3 ./tools/market_analysis.py --market-id 42  # Analyze specific market
python3 ./tools/place_order.py --market-id 42 --side buy --outcome yes --price 0.55 --amount 10
python3 ./tools/cancel_order.py --order-id order_abc123
python3 ./tools/pnl_tracker.py                  # Position values + unrealized P&L
python3 ./tools/ws_listener.py --duration 10    # Real-time event stream
python3 ./tools/ready_check.py                  # Pre-flight validation (config, network, balances)
python3 ./tools/vault_ops.py --action balance                      # Vault + wallet USDC balance
python3 ./tools/vault_ops.py --action balance --market-id 42       # Also show YES/NO share balances
python3 ./tools/vault_ops.py --action deposit --amount 100         # Deposit USDC into vault
python3 ./tools/vault_ops.py --action withdraw --amount 50         # Withdraw USDC from vault
python3 ./tools/vault_ops.py --action mint --market-id 42 --amount 10   # Mint 10 YES + 10 NO shares ($10)
python3 ./tools/vault_ops.py --action merge --market-id 42 --amount 5   # Merge 5 pairs back to $5 USDC
python3 ./tools/vault_ops.py --action claim --market-id 42         # Claim winnings after resolution
python3 ./tools/sign_order.py --type order --market-id 42 --side buy --outcome yes --price 0.55 --amount 10
```

## How Profits Work

Shares cost between $0.01 and $0.99. They pay $1 if the outcome happens, $0 if not.

| You do | You pay | You get if right | You get if wrong |
|--------|---------|------------------|------------------|
| Buy YES at 40c | $0.40/share | $1.00/share | $0.00 |
| Buy NO at 55c | $0.55/share | $1.00/share | $0.00 |
| Sell YES at 60c | Receive $0.60/share | Owe $1 (must own shares) | Keep $0.60 |
| Mint + sell both | $1.00 mint cost | Revenue from selling both sides | Same |

## Profit Strategies

### 1. Directional: Buy underpriced outcomes
Market says 40% player wins. You think it's 55%. Buy YES at 40c. If you're right, expected value = 0.55 × $1 - $0.40 = +$0.15 per share.

### 2. Market Making: Capture the spread
Buy YES at 45c, sell YES at 55c. Both fill → 10c profit per share, outcome-independent. Risk: one side fills and the other doesn't.

### 3. Arbitrage: Buy both sides cheap
YES ask 45c + NO ask 50c = 95c for a pair worth $1. Buy both → 5c risk-free per pair. `market_analysis.py` calculates this as `arbBuyBoth`.

### 4. Mint + Sell: Provide liquidity at a premium
Mint shares on-chain (1 USDC → 1 YES + 1 NO). Sell YES at 55c + NO at 55c = $1.10 revenue. 10c profit per pair. `arbMintSell` shows this edge.

### 5. Value Investing: Bet on probability shifts
Player dealt 20, dealer showing 5 → player wins 85%+. If market prices 60%, buy YES aggressively before the price catches up.

## Market Analysis Output

`market_analysis.py` gives you raw edge signals. Key fields:

| Field | What it means |
|-------|---------------|
| `arbBuyBoth` | % profit from buying YES + NO asks. Positive = arb exists. |
| `arbMintSell` | % profit from minting and selling into bids. Positive = LP opportunity. |
| `yesSpreadCapture` | $ per share from buying bid / selling ask on YES side |
| `noSpreadCapture` | $ per share from buying bid / selling ask on NO side |
| `yesNoSumPct` | Should be ~100%. Below = arb. Above = overpriced. |
| `orderbook.yesBidTopSize` | How many $ you can sell at best bid without moving the price |
| `volume` | Trading activity — higher = more opportunity, more competition |

## Platform

- **Chain**: Monad (143) | **RPC**: `https://rpc.monad.xyz`
- **Pricing**: Basis points (5000 = 50c = 50%). **USDC**: 6 decimals (1000000 = $1)
- **Phases**: BETTING (trade), LOCKED (no trading), RESOLVED (claim winnings)
- **Hands**: New every ~30 seconds. Each creates a market.

### Contracts

| Contract | Address |
|----------|---------|
| USDC | `0xDE6498947808BCcD50F18785Cc3B0C472380C1fB` |
| Vault | `0xd1a710199b84899856696Ce0AA30377fB7B485C3` |
| Exchange | `0xC628e81B506b572391669339c2AbaCFafa0d95dD` |

### API

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/state/{address}` | GET | Everything in one call |
| `/api/markets` | GET | Active markets |
| `/api/orderbook/{marketId}` | GET | Full order book |
| `/api/fair-price/{marketId}` | GET | Mid-market + spread |
| `/api/market-stats/{marketId}` | GET | Volume, depth, trade count |
| `/api/order` | POST | Place signed order |
| `/api/orders/batch` | POST | Up to 10 orders at once |
| `/api/order/{orderId}` | DELETE | Cancel (EIP-191 sig required) |
| `/api/order/{orderId}/status` | GET | Status + fill history |

### Order Signing

- **Orders**: EIP-712 with domain `{ name: "BlackjackExchange", version: "1", chainId, verifyingContract }`
- **Cancels**: EIP-191 on `Cancel order {orderId}\nTimestamp: {timestamp}`
- **Use the tools** — `place_order.py` and `cancel_order.py` handle signing automatically.

## Autonomous Mode

For continuous autonomous trading, see [HEARTBEAT.md](HEARTBEAT.md). The heartbeat runs a scan-analyze-trade-report cycle on each interval without waiting for user prompts.
