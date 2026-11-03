"""Tiny Vapi REST client used by the scripts. Reads VAPI_API_KEY from the environment."""
from __future__ import annotations

import os
from typing import Any, Dict

import httpx

BASE = "https://api.vapi.ai"


def client() -> httpx.Client:
    key = os.environ.get("VAPI_API_KEY")
    if not key:
        raise SystemExit("Set VAPI_API_KEY (your Vapi private key).")
    return httpx.Client(base_url=BASE, headers={"Authorization": f"Bearer {key}"}, timeout=30)


def check(r: httpx.Response) -> Dict[str, Any]:
    if r.status_code >= 400:
        raise SystemExit(f"Vapi API {r.request.method} {r.request.url.path} -> {r.status_code}: {r.text[:500]}")
    return r.json()
