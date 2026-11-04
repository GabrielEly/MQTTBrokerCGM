import json
import math
from datetime import datetime
from typing import Any, Union
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


SUPPORTED_UNITS = {"mg/dL", "mmol/L"}
REQUIRED_FIELDS = {"patient", "device", "time", "glucose", "unit"}


class ValidationError(ValueError):
    pass


def validate_payload(
    payload: Union[str, bytes, dict[str, Any]],
    timezone_name: str = "Asia/Shanghai",
) -> dict[str, Any]:
    if isinstance(payload, (str, bytes)):
        try:
            data = json.loads(payload)
        except (json.JSONDecodeError, UnicodeDecodeError) as error:
            raise ValidationError(f"invalid JSON: {error}") from error
    else:
        data = payload

    if not isinstance(data, dict):
        raise ValidationError("message must be a JSON object")
    missing = REQUIRED_FIELDS - data.keys()
    if missing:
        raise ValidationError(f"missing required field(s): {', '.join(sorted(missing))}")

    for name in ("patient", "device"):
        if not isinstance(data[name], str) or not data[name].strip():
            raise ValidationError(f"{name} must be a non-empty string")

    time_value = data["time"]
    if not isinstance(time_value, str) or not time_value.strip():
        raise ValidationError("time must be a non-empty ISO 8601 string")
    normalized_time = time_value.strip()
    if "T" not in normalized_time.upper():
        raise ValidationError("time must include a date and time")
    if normalized_time.endswith(("Z", "z")):
        normalized_time = normalized_time[:-1] + "+00:00"
    try:
        parsed_time = datetime.fromisoformat(normalized_time)
    except ValueError as error:
        raise ValidationError("time must be a valid ISO 8601 date-time") from error
    if parsed_time.tzinfo is None:
        try:
            parsed_time = parsed_time.replace(tzinfo=ZoneInfo(timezone_name))
        except ZoneInfoNotFoundError as error:
            raise ValidationError(f"unknown timezone: {timezone_name}") from error

    glucose = data["glucose"]
    if isinstance(glucose, bool) or not isinstance(glucose, (int, float)):
        raise ValidationError("glucose must be a finite number")
    if not math.isfinite(glucose) or glucose <= 0:
        raise ValidationError("glucose must be finite and greater than zero")

    unit = data["unit"]
    if not isinstance(unit, str) or unit not in SUPPORTED_UNITS:
        raise ValidationError(
            f"unit must be one of: {', '.join(sorted(SUPPORTED_UNITS))}"
        )

    return {
        "patient": data["patient"].strip(),
        "device": data["device"].strip(),
        "time": parsed_time.isoformat(),
        "glucose": glucose,
        "unit": unit,
    }
