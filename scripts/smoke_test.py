#!/usr/bin/env python3
"""Post-boot smoke test: HTTP health plus a real WebSocket round trip.

Run against an already-running server:

    python scripts/smoke_test.py [base_url]

This catches stack-level breakage that importing the app cannot: a Gunicorn
worker class that no longer exists, a bad Socket.IO async_mode, or a missing
WebSocket transport all leave the code perfectly importable but unable to
serve a request.
"""

import sys
import time
import urllib.request

import socketio

DEFAULT_BASE_URL = "http://127.0.0.1:5000"


def wait_for_health(base_url, timeout=60):
    """Poll /health until it answers 200 or the timeout expires."""
    deadline = time.time() + timeout
    last_error = None

    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"{base_url}/health", timeout=5) as response:
                if response.status == 200:
                    print("OK   /health returned 200")
                    return True
                last_error = f"status {response.status}"
        except Exception as exc:
            last_error = exc
        time.sleep(1)

    print(f"FAIL /health never became ready ({last_error})")
    return False


def check_websocket(base_url):
    """Connect to /scores over the websocket transport only.

    Polling still works when the WebSocket transport is broken, so allowing a
    fallback here would hide exactly the failure this test exists to find.
    """
    client = socketio.Client()
    try:
        client.connect(
            base_url,
            namespaces=["/scores"],
            transports=["websocket"],
            wait_timeout=15,
        )
        transport = client.transport()
        if transport != "websocket":
            print(f"FAIL negotiated transport was {transport!r}, expected 'websocket'")
            return False
        print("OK   /scores connected over websocket")
        return True
    except Exception as exc:
        print(f"FAIL websocket connection to /scores: {exc}")
        return False
    finally:
        try:
            client.disconnect()
        except Exception:
            pass


def main():
    base_url = (sys.argv[1] if len(sys.argv) > 1 else DEFAULT_BASE_URL).rstrip("/")
    print(f"Smoke testing {base_url}")

    passed = wait_for_health(base_url) and check_websocket(base_url)

    print("Smoke test passed" if passed else "Smoke test FAILED")
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
