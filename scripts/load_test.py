#!/usr/bin/env python3
"""Authenticated, tenant-scoped critical endpoint load test (never production)."""
import argparse
import concurrent.futures
import json
import statistics
import time
import urllib.error
import urllib.parse
import urllib.request


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--cookie", required=True, help="Non-production fleet session cookie")
    parser.add_argument("--users", type=int, default=10)
    parser.add_argument("--requests", type=int, default=100)
    args = parser.parse_args()
    host = urllib.parse.urlparse(args.base_url).hostname or ""
    if host not in {"127.0.0.1", "localhost"} and "preview" not in host and "staging" not in host:
        raise SystemExit("Refusing load test: target must be localhost, preview, or staging")
    endpoints = ["/api/dashboard", "/api/vehicles?page=1&page_size=25", "/api/trips?page=1&page_size=25", "/api/expenses?page=1&page_size=25"]

    def request(index):
        started = time.perf_counter()
        req = urllib.request.Request(args.base_url.rstrip("/") + endpoints[index % len(endpoints)], headers={"Cookie": args.cookie})
        try:
            with urllib.request.urlopen(req, timeout=15) as response:
                ok = 200 <= response.status < 400
        except (urllib.error.URLError, TimeoutError):
            ok = False
        return (time.perf_counter() - started) * 1000, ok

    with concurrent.futures.ThreadPoolExecutor(max_workers=args.users) as pool:
        results = list(pool.map(request, range(args.requests)))
    timings = sorted(item[0] for item in results)
    output = {
        "concurrency": args.users,
        "requests": args.requests,
        "median_ms": round(statistics.median(timings), 2),
        "p95_ms": round(timings[max(0, int(len(timings) * 0.95) - 1)], 2),
        "maximum_ms": round(max(timings), 2),
        "error_rate": round(sum(not item[1] for item in results) / len(results), 4),
    }
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
