"""URL Codec module — percent-encode and decode text for URLs."""
import urllib.parse

from skills.registry import register


@register("url_codec", [
    r"url\s+encode\s+(?P<body>.+)$",
    r"url\s+decode\s+(?P<body>.+)$",
], "Percent-encode or decode text for URLs")
def skill_url_codec(text, match):
    body = match.group("body").strip()
    if "encode" in match.group(0).lower():
        return "Encoded: " + urllib.parse.quote(body, safe="")
    return "Decoded: " + urllib.parse.unquote_plus(body)
