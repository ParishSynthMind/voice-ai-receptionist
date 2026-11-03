"""Print a Vapi call's status, transcript and tool calls (from Vapi's own log, not ours).

  python scripts/get_call.py CALL_ID [--json out.json]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from vapi_api import check, client  # noqa: E402


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("call_id")
    p.add_argument("--json", help="Save the call record (minus recording URLs) to this file")
    a = p.parse_args()
    with client() as c:
        call = check(c.get(f"/call/{a.call_id}"))
    print("status:", call.get("status"), "| ended:", call.get("endedReason"), "| cost:", call.get("cost"))
    for m in (call.get("artifact") or {}).get("messages") or call.get("messages") or []:
        role = m.get("role")
        if role in ("assistant", "bot", "user"):
            print(f"{'AGENT' if role != 'user' else 'CALLER'}: {m.get('message')}")
        elif role == "tool_calls":
            for tc in m.get("toolCalls") or []:
                print(f"  -> tool {tc['function']['name']}({tc['function']['arguments']})")
        elif role == "tool_call_result":
            print(f"  <- {m.get('result')}")
    if a.json:
        for k in ("recordingUrl", "stereoRecordingUrl"):
            call.pop(k, None)
            (call.get("artifact") or {}).pop(k, None)
        Path(a.json).write_text(json.dumps(call, indent=2))


if __name__ == "__main__":
    main()
