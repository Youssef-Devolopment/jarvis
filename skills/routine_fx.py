"""Exchange rates via open.er-api.com."""
from __future__ import annotations
import urllib.parse
from skills.registry import register
from skills.http_util import http_get
from logger import get_logger

log = get_logger(__name__)

CURRENCIES = {
    "usd":"USD","dollar":"USD","dollars":"USD","eur":"EUR","euro":"EUR","euros":"EUR",
    "gbp":"GBP","pound":"GBP","pounds":"GBP","egp":"EGP","egyptian pound":"EGP",
    "sar":"SAR","riyal":"SAR","saudi riyal":"SAR","aed":"AED","dirham":"AED",
    "jpy":"JPY","yen":"JPY","cny":"CNY","yuan":"CNY","rmb":"CNY",
    "inr":"INR","rupee":"INR","rupees":"INR","cad":"CAD","aud":"AUD",
    "chf":"CHF","try":"TRY","lira":"TRY",
}


@register("fx", [
    r"^(?:convert\s+)?(?P<amt>\d+(?:\.\d+)?)\s*"
    r"(?P<src>usd|eur|gbp|egp|sar|aed|jpy|cny|inr|cad|aud|chf|try|"
    r"dollars?|euros?|pounds?|riyals?|dirhams?|yen|yuan|rupees?|lira)"
    r"\s+(?:to|in|into)\s+"
    r"(?P<dst>usd|eur|gbp|egp|sar|aed|jpy|cny|inr|cad|aud|chf|try|"
    r"dollars?|euros?|pounds?|riyals?|dirhams?|yen|yuan|rupees?|lira)"
    r"[\?\.\!]?$",
], "Currency conversion")
def s_fx(text, m):
    try:
        amount = float(m.group("amt"))
        src = CURRENCIES.get(m.group("src").lower())
        dst = CURRENCIES.get(m.group("dst").lower())
        if not src or not dst:
            return None
        d = http_get("https://open.er-api.com/v6/latest/"
                 + urllib.parse.quote(src), as_json=True)
        rate = (d.get("rates") or {}).get(dst)
        if rate is None:
            return None
        return f"{amount:g} {src} = {amount*rate:.2f} {dst} (rate {rate:.4f})."
    except Exception:
        return None
