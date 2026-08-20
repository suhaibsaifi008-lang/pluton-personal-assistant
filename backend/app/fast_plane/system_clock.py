"""PLUTON V2 — Trusted System Clock Capability.

Authoritative source of reality for system date, time, and timezone calculations.
Decoupled from model hallucinations and physical desktop interactions.
"""

from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Any
import zoneinfo


class SystemClockEvaluator:
    """Deterministic system clock provider utilizing host runtime OS clock."""

    _OFFSET_MAP: dict[str, float] = {
        "utc": 0.0,
        "gmt": 0.0,
        "est": -5.0,
        "edt": -4.0,
        "cst": -6.0,
        "cdt": -5.0,
        "mst": -7.0,
        "mdt": -6.0,
        "pst": -8.0,
        "pdt": -7.0,
        "ist": 5.5,
        "bst": 1.0,
        "cet": 1.0,
        "cest": 2.0,
        "jst": 9.0,
        "asia/tokyo": 9.0,
        "america/new_york": -5.0,
        "america/los_angeles": -8.0,
        "america/chicago": -6.0,
        "europe/london": 0.0,
        "europe/paris": 1.0,
        "asia/kolkata": 5.5,
    }

    @classmethod
    def get_current_time(cls, timezone_str: str | None = None) -> dict[str, Any]:
        """Returns current trusted date and time, optionally in specified timezone."""
        now_utc = datetime.now(timezone.utc)
        target_tz = timezone.utc
        tz_name = "UTC"

        if timezone_str and timezone_str.strip():
            tz_query = timezone_str.strip().lower()
            resolved_tz = None

            # 1. Try standard zoneinfo
            try:
                resolved_tz = zoneinfo.ZoneInfo(timezone_str.strip())
                tz_name = timezone_str.strip()
            except Exception:
                # 2. Fallback to offset table for Windows systems without tzdata
                if tz_query in cls._OFFSET_MAP:
                    offset_hours = cls._OFFSET_MAP[tz_query]
                    resolved_tz = timezone(timedelta(hours=offset_hours))
                    tz_name = timezone_str.strip()

            if resolved_tz is None:
                return {
                    "success": False,
                    "error": f"Invalid or unrecognized timezone '{timezone_str}'",
                    "datetime_iso": now_utc.isoformat(),
                    "formatted_date": now_utc.strftime("%A, %B %d, %Y"),
                    "formatted_time": now_utc.strftime("%I:%M:%S %p UTC"),
                    "timezone": "UTC",
                    "timestamp_unix": now_utc.timestamp(),
                }
            target_tz = resolved_tz

        local_dt = now_utc.astimezone(target_tz)
        formatted_date = local_dt.strftime("%A, %B %d, %Y")
        formatted_time = local_dt.strftime("%I:%M %p").strip()
        message = f"Today is {formatted_date}, and the current time is {formatted_time}."

        return {
            "success": True,
            "datetime_iso": local_dt.isoformat(),
            "formatted_date": formatted_date,
            "formatted_time": formatted_time,
            "timezone": tz_name,
            "timestamp_unix": local_dt.timestamp(),
            "message": message,
        }
