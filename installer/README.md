# The JARVIS installer

`dist\JARVIS-Setup-<version>.exe` — a normal Windows installer. Download
it, double-click it, and JARVIS lands in `%LOCALAPPDATA%\Programs\JARVIS`
with a Start Menu entry and an uninstaller in Add/Remove Programs.

No admin rights are requested: everything is per-user, including the
autostart entry, so nothing asks for a UAC prompt.

## Build it

```powershell
winget install JRSoftware.InnoSetup      # once
powershell -ExecutionPolicy Bypass -File installer\build.ps1
```

`build.ps1` reads the version from `config.py` (the single source of
truth), generates the file list, compiles with Inno Setup 6 and leaves
`dist\JARVIS-Setup-<version>.exe` behind. In CI the same script runs on
every `v*` tag, which then **installs the artifact, asserts the package
contents, runs the dependency bootstrap for real and uninstalls it**
before uploading the installer as a workflow artifact.

## What the installer does

1. Copies the app into `%LOCALAPPDATA%\Programs\JARVIS`.
2. Creates the Start Menu entries — **JARVIS** (tray + Alt+Space HUD),
   **JARVIS (console)** (same thing with logs visible) and an uninstall
   entry.
3. Optionally: a desktop icon, and autostart on sign-in (a per-user
   `Run` key, removed again by the uninstaller).
4. Unless you untick it, builds the Python virtual environment:
   `.venv`, `pip install -r requirements.txt`, open-interpreter, and
   optionally the Playwright browser engine (~150 MB, untick it if you
   do not need browsing skills).
5. Copies `.env.example` to `.env` — only if there is no `.env`
   already. It never overwrites one.
6. Verifies that Flask and `config.py` import before declaring success.

If step 4 fails the app is still installed and the failure is reported
with the path to `logs\install.log`. It is idempotent, so the fix is to
install whatever was missing and run it again — no reinstall:

```powershell
powershell -ExecutionPolicy Bypass -File installer\install-deps.ps1
```

## What ships, and what can never ship

The file list is **generated from `git ls-files`**, not written by hand.
Only files tracked in the repository can be packaged. Everything the
project keeps out of git — `.env`, `.env.bak`, `logs/`, `voices/*.onnx`
(330 MB of local speech models), `memory/*.db`, `docs/research/`,
`mcp_servers.json`, `jarvis_config.json`, `library/user_catalog.json`,
`modules/state.json` — is therefore structurally impossible to ship.

`build.ps1` does not rely on that alone: it also scans the list for
`.env*`, `*.db`, `*.onnx`, `*.bak`, `logs/` and the other personal
paths, and **aborts the build** if any of them appear. A leaked key is
the one mistake in this folder that a later commit cannot undo.

`installer/` itself is excluded from the generated list and shipped
explicitly, so this file reaches installs without being packaged twice.

## Uninstalling

The uninstaller removes the program, the shortcuts, the autostart entry
and the virtual environment, and takes the entry out of Add/Remove
Programs. It also deletes `.env`, so your API keys do not sit on disk
after you have uninstalled — copy that file somewhere first if you
intend to reinstall.

It deliberately **keeps** `memory/` — that is your memory database, not
the program — and tells you where it is. Delete the folder by hand if
you want it gone too.

## Verifying a build

`TESTING.md` §"Installer" has the checklist. The short version: build,
then install into a throwaway folder with

```powershell
dist\JARVIS-Setup-<version>.exe /VERYSILENT /SUPPRESSMSGBOXES /DIR="%TEMP%\jarvis-install-test"
```

and confirm that `.env`, `logs\` and `voices\*.onnx` are **absent** from
the installed tree, that the shortcuts exist, and that the uninstaller
takes it all back out again.
