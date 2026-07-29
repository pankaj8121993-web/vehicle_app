#!/usr/bin/env python3
"""Guarded authenticated HTTP benchmark and multi-session load runner."""
import argparse
import concurrent.futures
import json
import os
import statistics
import time
import uuid
from collections import Counter
from urllib.parse import urlparse

import httpx
from passlib.hash import bcrypt
from pymongo import MongoClient


ENDPOINTS = {
    "dashboard": "/api/dashboard",
    "vehicles": "/api/vehicles?page=1&page_size=25",
    "vehicle_search": "/api/vehicles?page=1&page_size=25&search=PERF-a-0200",
    "vehicle_profile": "/api/vehicles/synthetic-perf-a-v-1/summary",
    "vehicle_statistics": "/api/vehicles/synthetic-perf-a-v-1/statistics",
    "drivers": "/api/drivers?page=1&page_size=25",
    "trips": "/api/trips?page=1&page_size=25",
    "trip_search": "/api/trips?page=1&page_size=25&search=Destination%209500",
    "expenses": "/api/expenses?page=1&page_size=25",
    "expense_search": "/api/expenses?page=1&page_size=25&search=Maintenance",
    "fuel": "/api/fuel?page=1&page_size=25",
    "fastag": "/api/fastag?page=1&page_size=25",
    "repairs": "/api/repairs?page=1&page_size=25",
    "exceptions": "/api/exceptions?page=1&page_size=25",
    "reports": "/api/reports",
}


def percentile(values, fraction):
    ordered = sorted(values)
    return ordered[max(0, min(len(ordered) - 1, int(len(ordered) * fraction) - 1))]


def guard(args):
    if urlparse(args.base_url).hostname not in {"127.0.0.1", "localhost"}:
        raise SystemExit("Refusing benchmark: HTTP target must be local")
    if not args.database.startswith("fleetflow_performance_"):
        raise SystemExit("Refusing benchmark: unsafe database name")
    if os.getenv("APP_ENV", "test").lower() == "production":
        raise SystemExit("Refusing benchmark in production")


def prepare(args):
    guard(args)
    password = os.environ.get("FLEETFLOW_PERF_PASSWORD")
    if not password or len(password) < 24:
        raise SystemExit("FLEETFLOW_PERF_PASSWORD (24+ characters) is required")
    mongo = MongoClient(args.mongo_url)
    db = mongo[args.database]
    for suffix in ("a", "b"):
        org = f"synthetic-perf-{suffix}"
        for index in range(5):
            username = f"perf_{suffix}_{index}"
            db.users.replace_one({"username": username}, {
                "id": str(uuid.uuid4()), "username": username,
                "password_hash": bcrypt.hash(password), "full_name": f"Synthetic Load User {suffix.upper()} {index}",
                "role": "owner", "org_id": org, "is_active": True, "is_demo": False,
                "must_change_password": False, "performance_fixture": True,
            }, upsert=True)
    mongo.close()
    print(json.dumps({"users": [f"perf_{s}_{i}" for s in ("a", "b") for i in range(5)]}))


def login(base_url, username, password):
    client = httpx.Client(base_url=base_url, timeout=20)
    response = client.post("/api/auth/login", json={"username": username, "password": password})
    response.raise_for_status()
    return client


def request(client, path):
    started = time.perf_counter()
    response = client.get(path)
    elapsed = (time.perf_counter() - started) * 1000
    return elapsed, response.status_code, len(response.content)


def benchmark(args):
    guard(args)
    password = os.environ["FLEETFLOW_PERF_PASSWORD"]
    client = login(args.base_url, "perf_a_0", password)
    output = {}
    for name, path in ENDPOINTS.items():
        for _ in range(args.warmup):
            client.get(path)
        samples = [request(client, path) for _ in range(args.requests)]
        times = [s[0] for s in samples]
        statuses = Counter(s[1] for s in samples)
        output[name] = {
            "requests": len(samples), "minimum_ms": round(min(times), 2),
            "median_ms": round(statistics.median(times), 2),
            "p95_ms": round(percentile(times, .95), 2), "maximum_ms": round(max(times), 2),
            "errors": sum(count for status, count in statuses.items() if status >= 400),
            "status": dict(statuses), "median_bytes": int(statistics.median(s[2] for s in samples)),
        }
    client.close()
    print(json.dumps(output, indent=2))


def load(args):
    guard(args)
    password = os.environ["FLEETFLOW_PERF_PASSWORD"]
    clients = [login(args.base_url, f"perf_{suffix}_{i}", password)
               for suffix in ("a", "b") for i in range(5)]
    paths = list(ENDPOINTS.values())
    identities = [client.get("/api/auth/me").json()["username"] for client in clients]
    tenant_checks = [
        clients[index].get(f"/api/vehicles/synthetic-perf-{'b' if index < 5 else 'a'}-v-1/summary").status_code
        for index in range(10)
    ]
    def one(index):
        client_index = index % len(clients)
        own_suffix = "a" if client_index < 5 else "b"
        path = paths[index % len(paths)].replace("synthetic-perf-a", f"synthetic-perf-{own_suffix}")
        return request(clients[client_index], path)
    started = time.perf_counter()
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as pool:
        samples = list(pool.map(one, range(args.load_requests)))
    duration = time.perf_counter() - started
    times = [s[0] for s in samples]
    statuses = Counter(s[1] for s in samples)
    for client in clients:
        client.close()
    print(json.dumps({
        "users": 10, "sessions": 10, "organisations": 2, "requests": len(samples),
        "duration_seconds": round(duration, 2), "requests_per_second": round(len(samples) / duration, 2),
        "minimum_ms": round(min(times), 2), "median_ms": round(statistics.median(times), 2),
        "p95_ms": round(percentile(times, .95), 2), "maximum_ms": round(max(times), 2),
        "errors": sum(count for status, count in statuses.items() if status >= 400),
        "status": dict(statuses), "separate_sessions": len(set(identities)) == 10,
        "tenant_concealment": tenant_checks == [404] * 10,
    }, indent=2))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("prepare", "benchmark", "load"))
    parser.add_argument("--base-url", default="http://127.0.0.1:8201")
    parser.add_argument("--database", required=True)
    parser.add_argument("--mongo-url", default="mongodb://127.0.0.1:27017")
    parser.add_argument("--requests", type=int, default=20)
    parser.add_argument("--warmup", type=int, default=3)
    parser.add_argument("--load-requests", type=int, default=200)
    args = parser.parse_args()
    {"prepare": prepare, "benchmark": benchmark, "load": load}[args.action](args)


if __name__ == "__main__":
    main()
