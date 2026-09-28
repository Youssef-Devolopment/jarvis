"""Test which models actually respond. Run: python test_models.py"""
from __future__ import annotations
import os, sys, time
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()
api_key = os.getenv("DEEPSEEK_API_KEY")
base_url = os.getenv("DEEPSEEK_BASE_URL")
if not api_key or not base_url:
    print("Missing DEEPSEEK_API_KEY or DEEPSEEK_BASE_URL in .env")
    sys.exit(1)

c = OpenAI(api_key=api_key, base_url=base_url)

candidates = [
    "deepseek-v4.1-flash:free",
    "deepseek-v4-flash:free",
    "mimo-v2.5:free",
    "deepseek-v3.2",
    "deepseek-v4-pro",
    "deepseek-reasoner",
    "deepseek-chat",
    "gpt-6-astra",
]

print(f"\nTesting {len(candidates)} models against {base_url}\n")
print(f"{'Model':<32} {'Status':<8} {'Time':<8} Reply")
print("-" * 90)

working = []
for mid in candidates:
    t0 = time.time()
    try:
        r = c.chat.completions.create(
            model=mid, max_tokens=10, temperature=0,
            messages=[{"role": "user", "content": "Say OK"}])
        reply = (r.choices[0].message.content or "").strip()[:40]
        ms = int((time.time() - t0) * 1000)
        print(f"{mid:<32} {'OK':<8} {ms}ms   {reply}")
        working.append(mid)
    except Exception as exc:
        msg = str(exc)[:50].replace("\n", " ")
        print(f"{mid:<32} {'FAIL':<8} {'--':<8} {msg}")

print("-" * 90)
print(f"\nWorking: {len(working)}/{len(candidates)}")
for m in working:
    print(f"  ✓ {m}")
print()
