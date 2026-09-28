"""Crypto prices via CoinGecko (free, no key)."""
from __future__ import annotations
import urllib.parse
from skills.registry import register
from skills.http_util import http_get
from logger import get_logger

log = get_logger(__name__)

# Common aliases -> CoinGecko IDs
COINS = {
    "bitcoin": "bitcoin", "btc": "bitcoin",
    "ethereum": "ethereum", "eth": "ethereum",
    "solana": "solana", "sol": "solana",
    "dogecoin": "dogecoin", "doge": "dogecoin",
    "cardano": "cardano", "ada": "cardano",
    "ripple": "ripple", "xrp": "ripple",
    "bnb": "binancecoin", "binance": "binancecoin",
    "polkadot": "polkadot", "dot": "polkadot",
    "polygon": "matic-network", "matic": "matic-network",
    "avalanche": "avalanche-2", "avax": "avalanche-2",
    "chainlink": "chainlink", "link": "chainlink",
    "tron": "tron", "trx": "tron",
    "shiba": "shiba-inu", "shib": "shiba-inu",
    "litecoin": "litecoin", "ltc": "litecoin",
}


def _price(symbol: str) -> str:
    cid = COINS.get(symbol.lower())
    if not cid:
        return None
    try:
        data = http_get("https://api.coingecko.com/api/v3/simple/price?"
                    + urllib.parse.urlencode({
                        "ids": cid, "vs_currencies": "usd",
                        "include_24hr_change": "true"}), as_json=True)
        info = data.get(cid, {})
        price = info.get("usd")
        change = info.get("usd_24h_change", 0)
        if price is None:
            return f"No price for {symbol}."
        arrow = "up" if change >= 0 else "down"
        return (f"{symbol.upper()} is ${price:,.2f}, "
                f"{arrow} {abs(change):.2f}% in 24 hours.")
    except Exception as exc:
        log.debug("Crypto failed: %s", exc)
        return None


@register("crypto", [
    r"\b(?:what(?:'s| is)\s+)?(?:the\s+)?(?:price\s+of\s+)?"
    r"(?P<coin>bitcoin|btc|ethereum|eth|solana|sol|dogecoin|doge|"
    r"cardano|ada|ripple|xrp|bnb|binance|polkadot|dot|polygon|matic|"
    r"avalanche|avax|chainlink|link|tron|trx|shiba|shib|litecoin|ltc)"
    r"(?:\s+price)?[\?\.\!]?$",
], "Crypto price")
def skill_crypto(text, m):
    coin = (m.group("coin") or "").strip().lower()
    if not coin:
        return None
    result = _price(coin)
    if not result:
        return None
    return result
