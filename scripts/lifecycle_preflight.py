from __future__ import annotations

import json
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.request import urlopen


base_url = (sys.argv[1] if len(sys.argv) > 1 else "http://51.250.95.80").rstrip("/")
routes = [
    "/",
    "/landing",
    "/knowledge",
    "/knowledge/dispute-resolution",
    "/privacy",
]


def fetch(path: str) -> tuple[int, bytes]:
    last_error = None
    for attempt in range(3):
        try:
            with urlopen(f"{base_url}{path}", timeout=15) as response:
                return response.status, response.read()
        except HTTPError as error:
            return error.code, error.read()
        except (URLError, OSError) as error:
            last_error = error
            if attempt < 2:
                time.sleep(1)
    reason = getattr(last_error, "reason", last_error)
    raise SystemExit(f"BLOCKED {path}: {reason}")


failures: list[str] = []
health_status, health_body = fetch("/api/health")
if health_status != 200:
    failures.append(f"/api/health returned {health_status}")
else:
    health = json.loads(health_body)
    if health.get("status") != "ok" or not health.get("version"):
        failures.append("/api/health has no ok status or version")
    else:
        print(f"PASS health: {health['version']}")

for route in routes:
    status, _ = fetch(route)
    if status == 200:
        print(f"PASS {route}")
    else:
        failures.append(f"{route} returned {status}")

if failures:
    for failure in failures:
        print(f"FAIL {failure}")
    raise SystemExit(1)

print("Preflight passed")
