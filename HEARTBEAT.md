# Trading Heartbeat

You are **blackjack-trader** running an autonomous heartbeat cycle. Execute these steps every cycle.

## Cycle

1. **Fetch state** — Run `python3 ./tools/fetch_state.py` to get balance, active markets, open positions, and pending orders.

2. **Analyze markets** — Run `python3 ./tools/market_analysis.py` to scan all active markets for edge signals (arbitrage, mispricing, wide spreads).

3. **Evaluate opportunities** — For each market with edge > 5%:
   - Size the trade per AGENTS.md rules (high edge = up to 20% of balance, medium = 10%, small = skip)
   - Check that total exposure stays under 70% of balance
   - Execute via `python3 ./tools/place_order.py`

4. **Log reasoning** — Before executing any trade, explain your decision in 2-3 sentences: what edge you see, why you're sizing this way, and what risk you're taking. For example: *"YES is priced at 40% but player has 20 vs dealer 6 — true probability is ~80%. Buying 10 shares at 0.42 for a 38c expected edge. Risk: dealer hits to 21, but that's <20% likely."* This reasoning trail is critical — it proves autonomous decision-making, not scripted logic.

5. **Cancel stale orders** — If any open orders are on markets about to lock (phase changing from BETTING), cancel them via `python3 ./tools/cancel_order.py`.

6. **Claim winnings** — If any positions are in RESOLVED markets, claim via `python3 ./tools/vault_ops.py --action claim --market-id ID`.

7. **Track P&L** — Run `python3 ./tools/pnl_tracker.py` to check cumulative performance against daily target.

8. **Report** — Respond with a one-line status: position count, P&L, any trades executed this cycle.

## Reference

Read [AGENTS.md](AGENTS.md) for full strategy details, risk limits, and sizing rules.
