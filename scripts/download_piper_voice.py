"""Download Piper voice models. Run once: python scripts/download_piper_voice.py"""
from __future__ import annotations
import os
import sys
import urllib.request
from pathlib import Path

VOICES_DIR = Path(__file__).resolve().parent.parent / "voices"
VOICES_DIR.mkdir(exist_ok=True)

BASE = "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_GB"

VOICES = [
    ("en_GB-alan-medium",         "alan"),
    ("en_GB-alba-medium",         "alba"),
    ("en_GB-northern_english_male-medium", "northern"),
]


def download(name: str, kind: str) -> bool:
    filename = f"{name}.onnx" if kind == "model" else f"{name}.onnx.json"
    # Repo layout: en/en_GB/<speaker>/<quality>/<file>
    short = name[len("en_GB-"):] if name.startswith("en_GB-") else name
    speaker, _, quality = short.rpartition("-")
    url = f"{BASE}/{speaker}/{quality}/{filename}"
    dest = VOICES_DIR / filename
    if dest.exists():
        print(f"  already exists: {filename}")
        return True
    print(f"  downloading {filename} …")
    try:
        urllib.request.urlretrieve(url, dest)
        print(f"  OK: {filename}  ({dest.stat().st_size // 1024} KB)")
        return True
    except Exception as exc:
        print(f"  FAILED: {exc}")
        return False


def main():
    print(f"Downloading Piper voices to {VOICES_DIR}\n")
    total_ok = 0
    for name, key in VOICES:
        print(f"[{key}] {name}")
        ok1 = download(name, "model")
        ok2 = download(name, "config")
        if ok1 and ok2:
            total_ok += 1
        print()
    print(f"Done. {total_ok}/{len(VOICES)} voices ready.")
    if total_ok == 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
