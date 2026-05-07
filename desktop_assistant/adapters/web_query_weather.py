from __future__ import annotations

import re
from typing import Any


WEATHER_MARKERS = ("weather", "天气", "气温", "降雨", "预报")
QUERY_FILLERS = (
    "查询",
    "查一下",
    "查找",
    "搜索",
    "今天",
    "今日",
    "现在",
    "当前",
    "的",
    "天气",
    "预报",
)


def _looks_like_weather_query(query: str) -> bool:
    lowered = query.lower()
    return any(marker in lowered for marker in WEATHER_MARKERS)


def _weather_location_from_query(query: str) -> str:
    lowered = query.lower().strip()
    match = re.search(r"\bweather\s+(?:in|for)\s+(?P<location>.+)$", lowered, re.IGNORECASE)
    if match is not None:
        return match.group("location").strip() or query

    location = query.strip()
    for filler in QUERY_FILLERS:
        location = location.replace(filler, "")
    location = location.strip(" ，。！？,.!?;:：")
    return location or query


def _format_weather_answer(location: str, payload: dict[str, Any]) -> str:
    current = _first_dict(payload.get("current_condition"))
    today = _first_dict(payload.get("weather"))
    if not current and not today:
        return ""

    desc = _weather_description(current) or _weather_description(today)
    temp = _field(current, "temp_C")
    feels_like = _field(current, "FeelsLikeC")
    humidity = _field(current, "humidity")
    wind = _field(current, "windspeedKmph")
    high = _field(today, "maxtempC")
    low = _field(today, "mintempC")

    parts = []
    if desc:
        parts.append(desc)
    if temp:
        parts.append(f"当前 {temp}°C")
    if feels_like:
        parts.append(f"体感 {feels_like}°C")
    if high or low:
        parts.append(f"最高/最低 {high or '-'}°C/{low or '-'}°C")
    if humidity:
        parts.append(f"湿度 {humidity}%")
    if wind:
        parts.append(f"风速 {wind} km/h")

    if not parts:
        return ""
    return f"{location}今日天气：" + "，".join(parts) + "。"


def _first_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, list) and value and isinstance(value[0], dict):
        return value[0]
    if isinstance(value, dict):
        return value
    return {}


def _field(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    return str(value).strip() if value not in (None, "") else ""


def _weather_description(payload: dict[str, Any]) -> str:
    for key in ("lang_zh", "weatherDesc"):
        value = payload.get(key)
        if isinstance(value, list):
            for item in value:
                if isinstance(item, dict) and str(item.get("value") or "").strip():
                    return str(item["value"]).strip()
        if isinstance(value, str) and value.strip():
            return value.strip()
    hourly = payload.get("hourly")
    if isinstance(hourly, list):
        for item in hourly:
            if isinstance(item, dict):
                desc = _weather_description(item)
                if desc:
                    return desc
    return ""
