from __future__ import annotations

from datetime import datetime, time, timedelta, timezone, tzinfo


def local_day_end_utc(now_utc: datetime, *, zone: tzinfo | None = None) -> datetime:
    """Exclusive UTC boundary of the current local calendar day.

    With no explicit zone, use the host OS timezone rules at the next local
    midnight (not a fixed offset copied from the current time). Persisted
    candidate contact timestamps are compared as UTC timestamps.
    """
    if now_utc.tzinfo is None:
        raise ValueError("now_utc must be timezone-aware")
    local_today = now_utc.astimezone(zone).date() if zone is not None else now_utc.astimezone().date()
    next_midnight = datetime.combine(local_today + timedelta(days=1), time.min)
    if zone is not None:
        next_midnight = next_midnight.replace(tzinfo=zone)
    return next_midnight.astimezone(timezone.utc)
