# blackjack-trader

Autonomous trading agent for blackjack prediction markets on Monad. Finds and captures profit through directional trading, market making, arbitrage, and liquidity provision.

## Get Started

**Point your AI agent at this repo** — it will handle installation automatically.

The agent reads [INSTALL.md](INSTALL.md), sets up a wallet, installs dependencies, and walks you through funding. You'll only need to approve a few transactions.

### Manual setup

```bash
cd agents/clawdbot
pip install -r requirements.txt
bash setup-agent.sh              # generate wallet
# Fund MON + USDC (see printed instructions)
bash setup-agent.sh --fund       # deposit into vault
python3 ./tools/ready_check.py   # verify everything works
```

## Usage

### Via slash command

```
/blackjack-trader scan for opportunities
/blackjack-trader buy YES on market 42 at 45 cents for $10
/blackjack-trader what's my P&L?
```

### Direct tool execution

```bash
python3 ./tools/fetch_state.py                  # Balance, markets, positions, orders
python3 ./tools/market_analysis.py               # Edge signals across all markets
python3 ./tools/place_order.py --market-id 42 --side buy --outcome yes --price 0.45 --amount 10
python3 ./tools/cancel_order.py --order-id order_abc123
python3 ./tools/pnl_tracker.py                   # P&L tracking
python3 ./tools/vault_ops.py --action balance     # On-chain balances
python3 ./tools/ready_check.py                    # Pre-flight validation
```

### Autonomous mode

See [HEARTBEAT.md](HEARTBEAT.md) for continuous autonomous trading cycles.

## Sideloading into OpenClaw

**Option A**: Copy into workspace skills (auto-detected)
```bash
cp -r agents/clawdbot skills/blackjack-trader
```

**Option B**: Add to `~/.openclaw/openclaw.json`
```json
{
  "skills": {
    "load": {
      "extraDirs": ["/path/to/not-a-casino/agents/clawdbot"],
      "watch": true
    }
  }
}
```

**Option C**: Symlink
```bash
ln -s /path/to/not-a-casino/agents/clawdbot ~/.openclaw/skills/blackjack-trader
```

## Architecture

Each tool is a standalone CLI script that outputs JSON to stdout. Config is loaded automatically: environment variables override `agent.env`, which overrides `config.json`.

The agent uses a ReAct loop: reason about market state, execute a tool, observe the output, repeat.

## Key Files

| File | Purpose |
|------|---------|
| [INSTALL.md](INSTALL.md) | Step-by-step installation (LLM-readable) |
| [SKILL.md](SKILL.md) | Tool reference + trading mechanics |
| [AGENTS.md](AGENTS.md) | Trading strategy + risk management |
| [HEARTBEAT.md](HEARTBEAT.md) | Autonomous trading cycle |
