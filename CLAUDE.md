# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running the App

```bash
pip install -r requirements.txt
python main.py
```

Requires KakaoTalk PC app installed and logged in. `pyautogui`/`pyperclip` must be installed for the send button to be active; the app starts and shows a warning banner if they are missing.

## Architecture

**KakaoTalk Blaster** is a tkinter desktop tool that lets academy admins bulk-send KakaoTalk messages to student parents. It reads student rosters and test scores from a Firebase Realtime Database (read-only — no writes) and automates KakaoTalk PC via GUI automation.

### Module responsibilities

| File | Role |
|------|------|
| `main.py` | Entry point — creates `tk.Tk()` and launches `KakaoAdminApp` |
| `app.py` | Entire GUI and orchestration — single `KakaoAdminApp` class |
| `firebase.py` | Firebase REST via stdlib `urllib` (no Firebase SDK); exposes `firebase_get/put/patch` |
| `kakao_send.py` | KakaoTalk automation via `pyautogui`/`pyperclip`; runs in a daemon thread |
| `template_engine.py` | Stateless `{변수}` interpolation; `render(template, ctx)` leaves undefined variables as-is |
| `settings.json` | Local config: `firebase_url`, `firebase_path`, `wait_time`, `room_prefix` |
| `templates.json` | User-created templates, persisted locally — independent of Firebase |

### Key patterns

**Threading model**: All Firebase calls and the KakaoTalk send loop run on `threading.Thread(daemon=True)`. UI updates from those threads must go through `self.root.after(0, callback)` — never touch tkinter widgets directly from a background thread.

**Firebase URL construction** (`firebase.py:_fb_url`): The node path is URL-encoded with `urllib.parse.quote(node, safe='/')`. The `scores/` node key for a class is `urllib.parse.quote(f"{sheet}|{cls}", safe="")` — the pipe character gets encoded to `%7C`.

**Template types**: Templates are either `"common"` (no score data) or `"score"` (reads `fb_scores`). Score-type templates activate the exam dropdown and silently exclude students with no score entry before sending.

**Send flow** (`kakao_send.py:send_messages`): Waits 3 seconds on thread start (for KakaoTalk window activation), then for each message: copies room name → `Ctrl/Cmd+F` → Esc → `Ctrl/Cmd+F` again → paste → Enter → copies message → paste → Enter → Esc.

**`AUTOMATION` flag**: `kakao_send.py` sets `AUTOMATION = True` only when `pyautogui` and `pyperclip` import successfully. `app.py` imports this flag to disable the send button when missing.

### Firebase data paths (read-only)

```
{firebase_path}/
  config/sheets/{M|T}/classes/{cls}/students  → [{name: "김상덕"}, ...]
  scores/{sheet}%7C{cls}/{testKey}/            → {type, round, date, max_score, students: {name: score}}
```

`testKey` format: `"{YYYY-MM-DD}|{type}|{round}"`. Exam dropdown is sorted by key descending (most recent first).
