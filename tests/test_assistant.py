from pathlib import Path

from receptionist.assistant import build_assistant

KB = Path(__file__).resolve().parent.parent / "data" / "knowledge_base.md"


def test_assistant_definition():
    a = build_assistant("Harbour Dental Clinic", "Europe/London", KB, "https://example.test/", "s3cret")
    assert a["model"]["provider"] == "anthropic" and a["model"]["model"].startswith("claude-")
    names = [t["function"]["name"] for t in a["model"]["tools"]]
    assert names == ["check_availability", "book_appointment", "send_summary", "handover"]
    for t in a["model"]["tools"]:
        assert t["server"]["url"] == "https://example.test/vapi/webhook"
        assert t["server"]["headers"] == {"x-vapi-secret": "s3cret"}
    prompt = a["model"]["messages"][0]["content"]
    assert "Free parking for patients" in prompt
    assert '{{"now" | date: "%A %d %B %Y", "Europe/London"}}' in prompt
    assert "end-of-call-report" in a["serverMessages"]


def test_transfer_tool_only_when_number_given():
    a = build_assistant("X", "UTC", KB, "https://e.test", None)
    assert all(t["type"] == "function" for t in a["model"]["tools"])
    assert "headers" not in a["server"]
    b = build_assistant("X", "UTC", KB, "https://e.test", None, transfer_number="+15550199")
    assert b["model"]["tools"][-1]["type"] == "transferCall"


def test_prompt_forbids_speaking_before_tool_results():
    a = build_assistant("X", "UTC", KB, "https://e.test", None)
    prompt = a["model"]["messages"][0]["content"]
    assert "Never state a time, a booking or a handover as done until the tool result has come back" in prompt
    assert all(t["messages"][0]["type"] == "request-start" for t in a["model"]["tools"])
