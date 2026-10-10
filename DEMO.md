# The 90-second JARVIS demo

This is the one flow to show people. It is short, it is reliable,
and every command in it was verified end-to-end on a clean session.
It covers all five product pillars in order — **voice, system
control, web, scheduling, local capture** — and ends on a moment
JARVIS *initiates itself*.

Total stage time: **under 90 seconds.** Prep: 2 minutes.

## Before you demo (2 min)

1. Start JARVIS (`desktop.bat`) and open the web UI — the topbar
   pill should read **READY** (green). Amber **ATTENTION** or red
   **SAFE MODE** still demos fine, but know why: click the pill,
   the SYSTEM tab explains it in one glance.
2. Quick pre-flight in a terminal (optional, 5 s):

   ```bat
   .venv\Scripts\python.exe check.py
   ```

   Exit 0 = everything. Exit 2 = skills-only mode — the demo still
   works minus AI chat and voice input (use the typed fallbacks).
3. Have the mic ready if you want the voice step: click **MIC** is
   push-to-talk (needs `GROQ_API_KEY`). No key? Type everything —
   the demo is identical.

## The script

| # | Time | You say / do | JARVIS does |
|---|------|--------------|-------------|
| 0 | 0:00 | Open the UI, gesture at the pill | Pill reads **READY**; greeting in the console; four starter chips under the wordmark |
| 1 | 0:05 | Click **MIC**, ask: *"What time is it?"* | Answers out loud, instantly: *"It is 10:42 — 10:42 AM."* (no key needed to answer; voice reply) |
| 2 | 0:20 | Type: `open notepad` | Notepad opens on your PC within a second |
| 3 | 0:35 | Type: `search the web for james webb telescope discoveries` | Streams a sourced answer with links, token by token |
| 4 | 0:60 | Type: `note: demo feedback - JARVIS is fast` | *"Noted in Obsidian"* — the thought is captured, not lost |
| 5 | 0:70 | Type: `remind me to drink water in 1 minute`, then turn to the audience | *"Reminder at 10:43"* — and ~60 s later, while you're wrapping up, **JARVIS interrupts with the spoken reminder on its own** |

Close with: *"That's the shape of it. Everything it did just now,
it can do on a schedule, by voice, or from an automation."*

If step 5's reminder lands mid-sentence — let it. That
self-initiated interrupt is the strongest beat in the demo.

## Fallbacks (nothing here is fragile)

| If… | Do this instead |
|---|---|
| No mic / no `GROQ_API_KEY` | Type `tell me the time` — same instant answer |
| No internet | Skip step 3; add `what time is it` + `open calculator` — local skills still shine |
| No `OBSIDIAN_VAULT` | Step 4 answers with its fallback ("saved to notes" path) — or swap for `remember: my go-to editor is vscode` and ask it back |
| Notepad blocked | `open calculator` — same instant system control |
| Pill shows ATTENTION / SAFE MODE | Click it, show the SYSTEM tab — *honest status* is part of the pitch |
| AI chat unavailable (exit 2) | The five commands above are all skill-powered; they work keyless |

## Recording a clip (optional artifact)

The scripted version doubles as the capture plan for a short
recording or GIF:

1. `Win+Alt+R` starts Windows screen recording (Xbox Game Bar).
2. Record ~60–90 s: pill at READY → MIC ask → the five commands.
3. Stop, then either keep it unlisted, or trim and drop it at
   `docs/overlay-demo.gif` and reference it in the README (the
   swap-in callout is already sitting in a comment there).
4. Stills for the landing page (`docs/screens/`): one shot of the
   main console with starter chips, one of the SYSTEM tab. The
   landing page in `docs/index.html` is designed to look complete
   without them.

## After the demo (cleanup)

- `close notepad` if you opened it in step 2.
- The 1-minute reminder is a one-off timer — nothing to clean up.
- Check the chat history panel: everything you just said is there,
  with a `/clear` if you want a fresh console (starter chips come
  back on a cleared console — nice for the next person).
