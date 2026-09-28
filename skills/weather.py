"""Weather via Open-Meteo (free, no key required)."""
from __future__ import annotations
import urllib.parse
from skills.registry import register
from skills.http_util import http_get
from logger import get_logger

log = get_logger(__name__)

WMO = {
    0:"clear sky", 1:"mainly clear", 2:"partly cloudy", 3:"overcast",
    45:"fog", 48:"freezing fog", 51:"light drizzle", 53:"drizzle",
    55:"heavy drizzle", 56:"freezing drizzle", 57:"freezing drizzle",
    61:"light rain", 63:"rain", 65:"heavy rain",
    66:"freezing rain", 67:"freezing rain",
    71:"light snow", 73:"snow", 75:"heavy snow", 77:"snow grains",
    80:"rain showers", 81:"rain showers", 82:"violent rain showers",
    85:"snow showers", 86:"snow showers",
    95:"thunderstorm", 96:"thunderstorm with hail", 99:"severe thunderstorm",
}


def _geocode(city: str):
    url = ("https://geocoding-api.open-meteo.com/v1/search?"
           + urllib.parse.urlencode({
               "name": city, "count": 1, "language": "en", "format": "json"}))
    data = http_get(url, as_json=True)
    results = data.get("results") or []
    return results[0] if results else None


def _format_current(city_name: str, data: dict) -> str:
    cur = data.get("current") or {}
    if not cur:
        return f"No weather data for {city_name}."
    temp = round(cur.get("temperature_2m", 0))
    feels = round(cur.get("apparent_temperature", temp))
    humidity = cur.get("relative_humidity_2m", 0)
    wind = round(cur.get("wind_speed_10m", 0))
    code = cur.get("weather_code", 0)
    desc = WMO.get(code, "unclear")
    return (f"In {city_name}: {temp}°C, {desc}. "
            f"Feels like {feels}°C, humidity {humidity}%, "
            f"wind {wind} km/h.")


@register("weather", [
    r"\b(?:what(?:'s| is)\s+(?:the\s+)?weather|how(?:'s| is)\s+the\s+weather|"
    r"weather(?:\s+(?:in|at|for)\s+(?P<city1>[A-Za-z][\w\s,'\-\.]+))?)",
    r"\b(?:forecast|temperature)(?:\s+(?:in|at|for)\s+(?P<city2>[A-Za-z][\w\s,'\-\.]+))?",
    r"\bhow\s+(?:hot|cold)\s+is\s+it(?:\s+in\s+(?P<city3>[A-Za-z][\w\s,'\-\.]+))?",
], "Weather report")
def skill_weather(text, m):
    gd = m.groupdict()
    city = (gd.get("city1") or gd.get("city2") or gd.get("city3") or "").strip(" ?.,")
    if not city:
        city = "Cairo"
    try:
        geo = _geocode(city)
        if not geo:
            return f"I could not find {city}."
        lat = geo["latitude"]
        lon = geo["longitude"]
        name = geo.get("name", city)
        country = geo.get("country", "")
        label = f"{name}, {country}" if country else name

        url = ("https://api.open-meteo.com/v1/forecast?"
               + urllib.parse.urlencode({
                   "latitude": lat, "longitude": lon,
                   "current": "temperature_2m,relative_humidity_2m,"
                              "apparent_temperature,wind_speed_10m,"
                              "weather_code",
                   "timezone": "auto"}))
        data = http_get(url, as_json=True)
        return _format_current(label, data)
    except Exception as exc:
        log.exception("Weather failed")
        return f"Weather lookup failed: {str(exc)[:80]}"
