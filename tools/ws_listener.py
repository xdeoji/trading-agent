#!/usr/bin/env python3
"""Connect to the exchange WebSocket and stream events.

Outputs JSON lines of received events for the specified duration.
"""

import argparse
import asyncio
import json
import sys
import time

from _config import load_config, output, error_exit


async def listen(ws_url: str, duration: int, event_filter: list[str] | None):
    """Connect to WebSocket and stream events."""
    try:
        import websockets
    except ImportError:
        error_exit("websockets package not installed. Run: pip install websockets")

    events = []
    start = time.time()

    try:
        async with websockets.connect(ws_url) as ws:
            # Print connection event
            events.append({"event": "connected", "url": ws_url, "timestamp": time.time()})

            while time.time() - start < duration:
                try:
                    remaining = duration - (time.time() - start)
                    if remaining <= 0:
                        break
                    raw = await asyncio.wait_for(ws.recv(), timeout=min(remaining, 5.0))
                    data = json.loads(raw)

                    # Apply filter if specified
                    if event_filter:
                        event_type = data.get("type", "")
                        if event_type not in event_filter:
                            continue

                    data["_receivedAt"] = time.time()
                    events.append(data)

                    # Print each event as a JSON line for streaming
                    print(json.dumps(data, default=str), flush=True)

                except asyncio.TimeoutError:
                    continue
                except Exception:
                    break

    except Exception as e:
        events.append({"event": "error", "error": str(e), "timestamp": time.time()})

    # Print summary to stderr so it doesn't mix with JSON lines on stdout
    summary = {
        "event": "summary",
        "totalEvents": len(events),
        "duration": round(time.time() - start, 1),
    }
    print(json.dumps(summary, default=str), flush=True)


def main():
    parser = argparse.ArgumentParser(description="Listen to exchange WebSocket events")
    parser.add_argument("--duration", type=int, default=30, help="Listen duration in seconds (default: 30)")
    parser.add_argument("--filter", nargs="*", help="Event types to include (e.g. trade market_created market_resolved)")
    args = parser.parse_args()

    cfg = load_config()
    ws_url = cfg["EXCHANGE_WS_URL"]

    asyncio.run(listen(ws_url, args.duration, args.filter))


if __name__ == "__main__":
    main()
