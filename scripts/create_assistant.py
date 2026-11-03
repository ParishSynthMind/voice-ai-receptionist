"""Create (or update) the receptionist assistant on Vapi and attach it to a phone number.

  python scripts/create_assistant.py --server-url https://your-host [--assistant-id ID] [--phone-number-id ID]
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from receptionist.assistant import build_assistant  # noqa: E402
from receptionist.config import Settings  # noqa: E402
from vapi_api import check, client  # noqa: E402


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--server-url", required=True, help="Public base URL of this service")
    p.add_argument("--assistant-id", help="Update this assistant instead of creating one")
    p.add_argument("--phone-number-id", help="Point this Vapi phone number at the assistant")
    p.add_argument("--transfer-number", default=os.environ.get("TRANSFER_NUMBER"))
    a = p.parse_args()
    s = Settings.from_env()
    body = build_assistant(s.business_name, s.timezone, s.knowledge_base, a.server_url, s.webhook_secret,
                           a.transfer_number)
    with client() as c:
        if a.assistant_id:
            assistant = check(c.patch(f"/assistant/{a.assistant_id}", json=body))
        else:
            assistant = check(c.post("/assistant", json=body))
        print("assistant", assistant["id"], assistant["model"]["provider"], assistant["model"]["model"])
        if a.phone_number_id:
            num = check(c.patch(f"/phone-number/{a.phone_number_id}", json={"assistantId": assistant["id"]}))
            print("phone number", num.get("number"), "->", assistant["id"])


if __name__ == "__main__":
    main()
