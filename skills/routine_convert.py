"""Unit conversions (length, weight, temperature)."""
from __future__ import annotations
from skills.registry import register
from logger import get_logger

log = get_logger(__name__)

# Base unit conversions (to base units)
LENGTH = {
    "mm": 0.001, "millimeter": 0.001, "millimeters": 0.001,
    "cm": 0.01, "centimeter": 0.01, "centimeters": 0.01,
    "m": 1.0, "meter": 1.0, "meters": 1.0,
    "km": 1000.0, "kilometer": 1000.0, "kilometers": 1000.0,
    "inch": 0.0254, "inches": 0.0254, "in": 0.0254,
    "ft": 0.3048, "foot": 0.3048, "feet": 0.3048,
    "yard": 0.9144, "yards": 0.9144, "yd": 0.9144,
    "mile": 1609.344, "miles": 1609.344, "mi": 1609.344,
}

WEIGHT = {
    "mg": 0.000001, "milligram": 0.000001, "milligrams": 0.000001,
    "g": 0.001, "gram": 0.001, "grams": 0.001,
    "kg": 1.0, "kilogram": 1.0, "kilograms": 1.0,
    "lb": 0.45359237, "lbs": 0.45359237, "pound": 0.45359237, "pounds": 0.45359237,
    "oz": 0.0283495, "ounce": 0.0283495, "ounces": 0.0283495,
    "ton": 1000.0, "tons": 1000.0, "tonne": 1000.0, "tonnes": 1000.0,
}


def _convert(amount, src, dst):
    src_l = src.lower()
    dst_l = dst.lower()
    # Temperature special case
    if src_l in ("c","celsius") or dst_l in ("c","celsius"):
        if src_l in ("c","celsius") and dst_l in ("f","fahrenheit"):
            return amount * 9/5 + 32, "°F"
        if src_l in ("f","fahrenheit") and dst_l in ("c","celsius"):
            return (amount - 32) * 5/9, "°C"
        if src_l in ("c","celsius") and dst_l in ("k","kelvin"):
            return amount + 273.15, "K"
        if src_l in ("f","fahrenheit") and dst_l in ("k","kelvin"):
            return (amount - 32) * 5/9 + 273.15, "K"
        if src_l in ("k","kelvin") and dst_l in ("c","celsius"):
            return amount - 273.15, "°C"
        if src_l in ("k","kelvin") and dst_l in ("f","fahrenheit"):
            return (amount - 273.15) * 9/5 + 32, "°F"
    # Length
    if src_l in LENGTH and dst_l in LENGTH:
        base = amount * LENGTH[src_l]
        return base / LENGTH[dst_l], dst
    # Weight
    if src_l in WEIGHT and dst_l in WEIGHT:
        base = amount * WEIGHT[src_l]
        return base / WEIGHT[dst_l], dst
    return None, None


@register("convert", [
    r"^(?:convert\s+)?(?P<amt>\d+(?:\.\d+)?)\s*"
    r"(?P<src>mm|cm|m|km|inch|inches|in|ft|foot|feet|yard|yards|yd|mile|miles|mi|"
    r"mg|g|kg|lb|lbs|pound|pounds|oz|ounce|ounces|ton|tons|tonne|tonnes|"
    r"c|celsius|f|fahrenheit|k|kelvin)\s+"
    r"(?:to|in|into)\s+"
    r"(?P<dst>mm|cm|m|km|inch|inches|in|ft|foot|feet|yard|yards|yd|mile|miles|mi|"
    r"mg|g|kg|lb|lbs|pound|pounds|oz|ounce|ounces|ton|tons|tonne|tonnes|"
    r"c|celsius|f|fahrenheit|k|kelvin)"
    r"[\?\.\!]?$",
], "Unit conversion")
def s_convert(text, m):
    try:
        amount = float(m.group("amt"))
        src = m.group("src")
        dst = m.group("dst")
        result, unit = _convert(amount, src, dst)
        if result is None:
            return None
        return f"{amount:g} {src} = {result:.4g} {unit}."
    except Exception:
        return None
