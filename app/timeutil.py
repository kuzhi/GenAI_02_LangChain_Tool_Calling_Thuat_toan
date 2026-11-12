from datetime import datetime, timedelta, timezone

# Múi giờ của kho (UTC+7). Giờ mở cửa 08:00-18:00 tính theo múi giờ này.
WAREHOUSE_TZ = timezone(timedelta(hours=7))


def now_utc() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def parse_aware(value: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Thời gian không được để trống")
    try:
        parsed = datetime.fromisoformat(value.strip())
    except ValueError:
        raise ValueError(f"Thời gian '{value}' không đúng định dạng ISO 8601") from None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"Thời gian '{value}' thiếu múi giờ (ví dụ +07:00)")
    return parsed


def to_utc_naive(value: datetime) -> datetime:
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def from_utc_naive(value: datetime, tz=timezone.utc) -> datetime:
    return value.replace(tzinfo=timezone.utc).astimezone(tz)
