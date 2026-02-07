# Installation

You are installing **blackjack-trader**, an autonomous trading agent for blackjack prediction markets on Monad.

Follow these steps in order. Steps marked **[ASK USER]** require human input — pause and ask before continuing.

## Step 1: Install dependencies

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Requires Python 3.10+ and [Foundry](https://book.getfoundry.sh/getting-started/installation) (`cast` CLI). If `cast` is not installed:
```bash
curl -L https://foundry.paradigm.xyz | bash && foundryup
```

**Note:** The virtual environment is required on macOS (which blocks global pip installs). All subsequent `python3` commands must run inside this venv. If commands fail with import errors, re-activate with `source venv/bin/activate`.

## Step 2: Generate wallet

```bash
bash setup-agent.sh
```

This creates `agent.env` with a fresh wallet (private key + address). All tools auto-discover this file — no need to export env vars manually.

Note the **Address** printed. You'll need it for funding.

## Step 3: Fund MON (gas) **[ASK USER]**

The agent needs MON to pay for on-chain transactions. Ask the user which option they prefer:

**Option A — Moltbook faucet** (50 MON, free): The user posts the agent address at the [Monad Foundation faucet](https://www.moltbook.com/post/74fcca14-4208-48cf-9808-25dcb1036e63). Requires a Moltbook account and a fresh address.

**Option B — Transfer from user's wallet**: The user provides their private key or sends MON themselves:
```bash
cast send AGENT_ADDRESS --value 1ether --rpc-url https://rpc.monad.xyz --private-key USER_KEY
```

Wait for the user to confirm MON has been sent before proceeding.

## Step 4: Fund USDC **[ASK USER]**

Ask the user to transfer USDC to the agent address. They can do this from their own wallet:
```bash
cast send 0xDE6498947808BCcD50F18785Cc3B0C472380C1fB \
  "transfer(address,uint256)" AGENT_ADDRESS AMOUNT \
  --rpc-url https://rpc.monad.xyz --private-key USER_KEY
```

Amount is in 6-decimal raw units (500000000 = 500 USDC). Wait for confirmation.

## Step 5: Deposit into Vault

```bash
bash setup-agent.sh --fund
```

This approves USDC and deposits it into the trading vault. A ready check runs automatically at the end. All checks should PASS:

```
  [+] DEPS     PASS
  [+] CONFIG   PASS
  [+] NETWORK  PASS
  [+] RPC      PASS
  [+] MON      PASS
  [+] VAULT    PASS

  GREEN LIGHT — ready to trade
```

If NETWORK fails, the exchange service may not be running — this is OK for setup, trading will work once it's live.

## Step 6: Start trading

Read SKILL.md for available tools and AGENTS.md for trading strategy. Then:

```bash
python3 ./tools/fetch_state.py        # Check balance and active markets
python3 ./tools/market_analysis.py     # Scan for trading opportunities
```

For autonomous operation, see [HEARTBEAT.md](HEARTBEAT.md).

## Troubleshooting

Run the ready check anytime to diagnose issues:
```bash
python3 ./tools/ready_check.py
```

If you get `ModuleNotFoundError`, re-activate the venv:
```bash
source venv/bin/activate
```

---

## Manual Install (without an AI agent)

If you're setting this up yourself rather than through an agent:

1. `python3 -m venv venv && source venv/bin/activate`
2. `pip install -r requirements.txt`
3. `bash setup-agent.sh` — generates wallet + `agent.env`
4. Fund MON (faucet or transfer) and USDC to the printed address
5. `bash setup-agent.sh --fund` — deposits USDC into vault
6. `python3 ./tools/ready_check.py` — verify everything works
7. Start trading with `/blackjack-trader scan for opportunities`
