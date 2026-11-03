"""FastAPI service Vapi talks to: tool calls in, spoken results out, and every call logged."""
from __future__ import annotations

import hmac
import json
import logging
from typing import Any, Dict, Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import PlainTextResponse

from .calendar.local import LocalCalendar
from .calllog import CallLog
from .config import Settings
from .notify import Notifier, OutboxNotifier, SmtpNotifier
from .scheduling import Scheduler
from .tools import Receptionist

log = logging.getLogger("receptionist")


def build_receptionist(settings: Settings, calendar=None, notifier: Optional[Notifier] = None) -> Receptionist:
    if calendar is None:
        if settings.calendar_backend == "google":
            from .calendar.google import GoogleCalendar, service_account_token_provider
            info = json.loads(settings.google_service_account_json) if settings.google_service_account_json else None
            calendar = GoogleCalendar(settings.google_calendar_id,
                                      service_account_token_provider(settings.google_service_account_file, info),
                                      timezone=settings.timezone)
        else:
            calendar = LocalCalendar(settings.data_dir / "calendar.sqlite3")
    if notifier is None:
        if settings.smtp_host and settings.team_email:
            notifier = SmtpNotifier(settings.smtp_host, settings.smtp_port, settings.smtp_user,
                                    settings.smtp_password, settings.smtp_from, settings.team_email)
        else:
            notifier = OutboxNotifier(settings.data_dir / "outbox.jsonl")
    scheduler = Scheduler(calendar, settings.timezone, settings.hours, settings.slot_minutes,
                          settings.min_notice_minutes)
    return Receptionist(scheduler, calendar, notifier, CallLog(settings.data_dir / "calls.sqlite3"),
                        settings.business_name)


def _args(raw: Any) -> Dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str) and raw.strip():
        try:
            value = json.loads(raw)
            return value if isinstance(value, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}


def _report(message: Dict[str, Any]) -> Dict[str, Any]:
    artifact = message.get("artifact") or {}
    analysis = message.get("analysis") or {}
    return {
        "started_at": message.get("startedAt"),
        "ended_at": message.get("endedAt"),
        "ended_reason": message.get("endedReason"),
        "duration_seconds": message.get("durationSeconds"),
        "cost": message.get("cost"),
        "transcript": artifact.get("transcript") or message.get("transcript"),
        "summary": analysis.get("summary") or message.get("summary"),
    }


def create_app(settings: Optional[Settings] = None, receptionist: Optional[Receptionist] = None) -> FastAPI:
    settings = settings or Settings.from_env()
    rec = receptionist or build_receptionist(settings)
    app = FastAPI(title="Voice AI Receptionist")
    app.state.receptionist = rec

    def check_secret(request: Request) -> None:
        if settings.webhook_secret:
            given = request.headers.get("x-vapi-secret", "")
            if not hmac.compare_digest(given, settings.webhook_secret):
                raise HTTPException(status_code=401, detail="bad secret")

    @app.get("/health")
    def health() -> Dict[str, str]:
        return {"status": "ok"}

    @app.post("/vapi/webhook")
    async def webhook(request: Request) -> Dict[str, Any]:
        check_secret(request)
        payload = await request.json()
        message = payload.get("message") or {}
        kind = message.get("type")
        call = message.get("call") or {}
        call_id = call.get("id")
        if call_id:
            rec.log.call_seen(call_id, call.get("type"), (call.get("customer") or {}).get("number"))

        if kind == "tool-calls":
            results = []
            for tc in message.get("toolCallList") or []:
                fn = tc.get("function") or {}
                name = fn.get("name") or tc.get("name")
                args = _args(fn.get("arguments", tc.get("arguments")))
                result = rec.run(name, args, call)
                log.info("tool %s -> %s", name, result)
                results.append({"toolCallId": tc.get("id"), "name": name, "result": result})
            return {"results": results}

        if kind == "end-of-call-report" and call_id:
            rec.log.end_of_call(call_id, _report(message))
        return {"ok": True}

    @app.get("/calls")
    def calls(request: Request, limit: int = 20):
        check_secret(request)
        return rec.log.calls(limit)

    @app.get("/calendar.ics", response_class=PlainTextResponse)
    def ics(request: Request):
        check_secret(request)
        export = getattr(rec.calendar, "export_ics", None)
        if export is None:
            raise HTTPException(status_code=404, detail="calendar backend has no .ics export")
        return PlainTextResponse(export(settings.business_name), media_type="text/calendar")

    return app
