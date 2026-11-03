import json

import pytest
from fastapi.testclient import TestClient

from receptionist.app import create_app
from receptionist.config import Settings

SECRET = "test-secret"
CALL = {"id": "call-9", "type": "inboundPhoneCall", "customer": {"number": "+15550100"}}


@pytest.fixture
def client(tmp_path, receptionist):
    app = create_app(Settings(data_dir=tmp_path, webhook_secret=SECRET), receptionist=receptionist)
    return TestClient(app)


def tool_call(name, args, as_string=False):
    return {"message": {"type": "tool-calls", "call": CALL, "toolCallList": [
        {"id": "tc-1", "type": "function",
         "function": {"name": name, "arguments": json.dumps(args) if as_string else args}}]}}


def post(client, body, secret=SECRET):
    return client.post("/vapi/webhook", json=body, headers={"x-vapi-secret": secret} if secret else {})


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_rejects_missing_or_wrong_secret(client):
    assert post(client, tool_call("check_availability", {}), secret=None).status_code == 401
    assert post(client, tool_call("check_availability", {}), secret="nope").status_code == 401


@pytest.mark.parametrize("as_string", [False, True])
def test_tool_call_round_trip(client, as_string):
    r = post(client, tool_call("check_availability", {"date": "tomorrow"}, as_string))
    assert r.status_code == 200
    res = r.json()["results"][0]
    assert res["toolCallId"] == "tc-1" and res["name"] == "check_availability"
    assert "2025-11-04" in res["result"]


def test_every_tool_over_http(client, notifier):
    book = {"name": "Sam", "phone": "1", "reason": "Clean", "date": "2025-11-04", "time": "14:00"}
    assert post(client, tool_call("book_appointment", book)).json()["results"][0]["result"].startswith("Booked.")
    assert post(client, tool_call("send_summary", {"summary": "s"})).json()["results"][0]["result"] == \
        "Summary sent to the team."
    assert "alerted" in post(client, tool_call("handover", {"reason": "wants a person"})).json()["results"][0]["result"]
    assert len(notifier.sent) == 2


def test_multiple_tool_calls_in_one_message(client):
    body = tool_call("check_availability", {})
    body["message"]["toolCallList"].append({"id": "tc-2", "function": {"name": "check_availability",
                                                                       "arguments": {"date": "friday"}}})
    ids = [r["toolCallId"] for r in post(client, body).json()["results"]]
    assert ids == ["tc-1", "tc-2"]


def test_end_of_call_report_is_logged(client):
    post(client, tool_call("book_appointment", {"name": "Sam", "phone": "1", "reason": "Clean",
                                                "date": "2025-11-04", "time": "15:00"}))
    report = {"message": {"type": "end-of-call-report", "call": CALL, "endedReason": "customer-ended-call",
                          "startedAt": "2025-11-03T08:00:00Z", "endedAt": "2025-11-03T08:02:00Z",
                          "durationSeconds": 120, "cost": 0.21,
                          "artifact": {"transcript": "AI: Hello\nUser: Hi"}, "analysis": {"summary": "Booked."}}}
    assert post(client, report).json() == {"ok": True}
    calls = client.get("/calls", headers={"x-vapi-secret": SECRET}).json()
    c = calls[0]
    assert c["call_id"] == "call-9" and c["caller"] == "+15550100" and c["ended_reason"] == "customer-ended-call"
    assert c["transcript"].startswith("AI: Hello") and c["outcome"].startswith("Booked")
    assert c["tool_events"][0]["tool"] == "book_appointment"


def test_ics_export(client):
    post(client, tool_call("book_appointment", {"name": "Sam", "phone": "1", "reason": "Clean",
                                                "date": "2025-11-04", "time": "16:00"}))
    r = client.get("/calendar.ics", headers={"x-vapi-secret": SECRET})
    assert r.status_code == 200 and "SUMMARY:Sam: Clean" in r.text
    assert client.get("/calendar.ics").status_code == 401
