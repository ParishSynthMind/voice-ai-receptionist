"""AI disclosure (EU AI Act Art. 50): the caller hears it first, once per call, and again on handover."""
from pathlib import Path

from receptionist.assistant import build_assistant
from receptionist.config import Settings
from receptionist.disclosure import DEFAULT_HANDOVER

KB = Path(__file__).resolve().parent.parent / "data" / "knowledge_base.md"
CALL = {"id": "call-1", "customer": {"number": "+44 7700 900123"}}


def _assistant(settings, transfer_number=None):
    return build_assistant(settings.business_name, "UTC", KB, "https://e.test", None, transfer_number,
                           disclosure=settings.disclosure, handover_notice=settings.handover_notice)


def test_default_disclosure_is_the_first_thing_the_caller_hears():
    a = _assistant(Settings(business_name="Harbour Dental Clinic"))
    assert a["firstMessage"].startswith("Hi, this is Elliot, an AI assistant for Harbour Dental Clinic.")
    assert "AI assistant" in a["model"]["messages"][0]["content"]


def test_default_used_by_build_assistant_without_settings():
    a = build_assistant("X Clinic", "UTC", KB, "https://e.test", None)
    assert "an AI assistant for X Clinic" in a["firstMessage"]


def test_custom_disclosure_text_and_name():
    s = Settings(business_name="Bay Vets", agent_name="Ava",
                 ai_disclosure="Hello, I'm {name}, the AI assistant at {business}.")
    assert _assistant(s)["firstMessage"].startswith("Hello, I'm Ava, the AI assistant at Bay Vets.")


def test_blank_disclosure_without_written_request_falls_back(monkeypatch):
    monkeypatch.setenv("AI_DISCLOSURE", "   ")
    monkeypatch.delenv("AI_DISCLOSURE_REMOVED_BY_WRITTEN_REQUEST", raising=False)
    s = Settings.from_env()
    assert "an AI assistant for" in _assistant(s)["firstMessage"]
    assert s.handover_notice == DEFAULT_HANDOVER


def test_removed_only_with_recorded_written_request(monkeypatch):
    monkeypatch.setenv("AI_DISCLOSURE", "")
    monkeypatch.setenv("AI_DISCLOSURE_REMOVED_BY_WRITTEN_REQUEST", "2026-11-17 email from J. Client")
    s = Settings.from_env()
    a = _assistant(s)
    assert "AI assistant for" not in a["firstMessage"] and a["firstMessage"].startswith("Hello")
    assert s.handover_notice == ""


def test_disclosure_not_repeated_in_ordinary_tool_results(receptionist):
    out = receptionist.run("check_availability", {"date": "tomorrow"}, CALL)
    assert "AI assistant" not in out


def test_handover_tells_the_caller_an_ai_is_passing_them_to_a_person(receptionist):
    out = receptionist.run("handover", {"caller_name": "Jo", "reason": "wants a person"}, CALL)
    assert out.startswith(DEFAULT_HANDOVER)


def test_handover_in_a_second_call_discloses_again(receptionist):
    receptionist.run("handover", {"reason": "a"}, CALL)
    out = receptionist.run("handover", {"reason": "b"}, {"id": "call-2"})
    assert "AI assistant" in out


def test_live_transfer_message_discloses():
    a = _assistant(Settings(), transfer_number="+15550199")
    msg = a["model"]["tools"][-1]["destinations"][0]["message"]
    assert msg.startswith(DEFAULT_HANDOVER) and "person" in msg


def test_service_wires_the_handover_notice_from_settings(tmp_path):
    from receptionist.app import build_receptionist
    r = build_receptionist(Settings(data_dir=tmp_path))
    assert r.handover_notice == DEFAULT_HANDOVER
    r2 = build_receptionist(Settings(data_dir=tmp_path, ai_disclosure_removed_by_written_request="2026-11-17 ref"))
    assert r2.handover_notice == ""
