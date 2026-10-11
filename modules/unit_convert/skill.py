"""Unit Converter module — length, weight and temperature math."""
from skills.registry import register

_LEN = {  # unit -> meters
    "km": 1000.0, "kilometer": 1000.0, "kilometers": 1000.0,
    "m": 1.0, "meter": 1.0, "meters": 1.0,
    "cm": 0.01, "centimeter": 0.01, "centimeters": 0.01,
    "mm": 0.001, "millimeter": 0.001, "millimeters": 0.001,
    "mi": 1609.344, "mile": 1609.344, "miles": 1609.344,
    "ft": 0.3048, "foot": 0.3048, "feet": 0.3048,
    "yd": 0.9144, "yard": 0.9144, "yards": 0.9144,
}
_W = {  # unit -> kilograms
    "kg": 1.0, "kilo": 1.0, "kilos": 1.0, "kilogram": 1.0,
    "kilograms": 1.0,
    "g": 0.001, "gram": 0.001, "grams": 0.001,
    "mg": 0.000001,
    "lb": 0.45359237, "lbs": 0.45359237, "pound": 0.45359237,
    "pounds": 0.45359237,
    "oz": 0.028349523, "ounce": 0.028349523, "ounces": 0.028349523,
    "ton": 1000.0, "tonne": 1000.0, "tonnes": 1000.0,
}
_TEMP = {"c": "C", "celsius": "C", "centigrade": "C",
         "f": "F", "fahrenheit": "F",
         "k": "K", "kelvin": "K"}
_HINT = ("I convert length (km, m, mi, ft, yd), weight (kg, g, lb, oz) "
         "and temperature (C, F, K) — try \"convert 5 km to miles\".")


def _temp(value, src, dst):
    c = value - 273.15 if src == "K" else \
        (value - 32.0) * 5.0 / 9.0 if src == "F" else value
    if dst == "K":
        out = c + 273.15
    elif dst == "F":
        out = c * 9.0 / 5.0 + 32.0
    else:
        out = c
    return f"{value:g} degrees {src} is {out:.2f} degrees {dst}."


def _convert(value, src, dst):
    s, d = src.lower(), dst.lower()
    if s in _TEMP and d in _TEMP:
        return _temp(value, _TEMP[s], _TEMP[d])
    if s in _LEN and d in _LEN:
        return f"{value:g} {src} is {value * _LEN[s] / _LEN[d]:.2f} {dst}."
    if s in _W and d in _W:
        return f"{value:g} {src} is {value * _W[s] / _W[d]:.2f} {dst}."
    return None


@register("unit_convert", [
    r"convert\s+(-?\d+(?:\.\d+)?)\s*([a-zA-Z]+)\s+(?:to|into)\s+([a-zA-Z]+)",
    r"what\s+is\s+(-?\d+(?:\.\d+)?)\s*([a-zA-Z]+)\s+in\s+([a-zA-Z]+)\b",
], "Convert length, weight and temperature units")
def skill_unit_convert(text, match):
    value = float(match.group(1))
    reply = _convert(value, match.group(2), match.group(3))
    return reply or _HINT
