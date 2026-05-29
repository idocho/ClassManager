# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running the App

```bash
pip install -r requirements.txt
python main.py
```

Requires KakaoTalk PC app installed and logged in. `pyautogui`/`pyperclip` must be installed for the send button to be active; the app starts and shows a warning banner if they are missing.

## Architecture

**ClassManager** is a tkinter desktop tool that lets academy admins manage a student roster and bulk-send KakaoTalk messages to student parents. It reads **and writes** student rosters / classes in a Firebase Realtime Database and automates KakaoTalk PC via GUI automation. (Test scores under `scores/` remain read-only.)

### Module responsibilities

| File | Role |
|------|------|
| `main.py` | Entry point — creates `tk.Tk()` and launches `ClassManagerApp` |
| `app.py` | Entire GUI and orchestration — single `ClassManagerApp` class |
| `firebase.py` | Firebase REST via stdlib `urllib` (no Firebase SDK); exposes `firebase_get/put/patch/delete` |
| `kakao_send.py` | KakaoTalk automation via `pyautogui`/`pyperclip`; runs in a daemon thread |
| `template_engine.py` | Stateless `{변수}` interpolation; `render(template, ctx)` leaves undefined variables as-is |
| `settings.json` | Local config: `dbUrl`, `dbPath`, `wait_time`, `room_prefix` |
| `templates.json` | User-created templates, persisted locally — independent of Firebase |

### Key patterns

**Threading model**: All Firebase calls and the KakaoTalk send loop run on `threading.Thread(daemon=True)`. UI updates from those threads must go through `self.root.after(0, callback)` — never touch tkinter widgets directly from a background thread.

**Firebase URL construction** (`firebase.py:_fb_url`): Reads `dbUrl`/`dbPath` from config (falls back to legacy `firebase_url`/`firebase_path` keys). **Both** the path and the node are URL-encoded with `urllib.parse.quote(..., safe='/')`, so a Korean/spaced `dbPath` works. The `scores/` node key for a class is `urllib.parse.quote(f"{sheet}|{cls}", safe="")` — the pipe character gets encoded to `%7C`.

**Background-thread error reporting**: status callbacks fired from `except Exception as e:` inside a `root.after(0, lambda ...)` MUST bind `lambda e=e:` — Python clears the `except` name on block exit, so an unbound `lambda: ...{e}` raises `NameError` and masks the real error.

**Roster CSV import** (`app.py:_import_csv`): CSV header is `출결번호,name,class` (UTF-8-sig). On upload it overwrites the whole `students/` node, then **auto-creates any class referenced by a student but missing from `classes/`** (via `firebase_patch`, preserving existing class groups). Group for new classes is inferred by `_infer_group`: contains `개별화` → `T`; else trailing `M`/`T` of the class code; else `M`. This makes a brand-new `dbPath` fully usable from a single CSV import.

**Student add form** (`app.py:_ask_student_form`): a single modal `Toplevel` collects 출결번호 + 이름 together (not two sequential `simpledialog` prompts). 출결번호 is the `nameKey`.

**Template types**: Templates are either `"common"` (no score data) or `"score"` (reads `fb_scores`). Score-type templates activate the exam dropdown and silently exclude students with no score entry before sending.

**Send flow** (`kakao_send.py:send_messages`): Waits 3 seconds on thread start (for KakaoTalk window activation), then for each message: copies room name → `Ctrl/Cmd+F` → Esc → `Ctrl/Cmd+F` again → paste → Enter → copies message → paste → Enter → Esc.

**`AUTOMATION` flag**: `kakao_send.py` sets `AUTOMATION = True` only when `pyautogui` and `pyperclip` import successfully. `app.py` imports this flag to disable the send button when missing.

### Firebase data paths (v2.0 — student-centric)

```
{dbPath}/
  students/{nameKey}        → {name, class}          # nameKey = 출결번호 (unique); class = classId or null
  classes/{classId}         → {group: "M"|"T", ...}  # roster groups; classId is the human class name
  scores/weekly/{classId}/  → {subject: {testKey: {type, round, date, max_score, students: {name: score}}}}
```

A student appears in the roster/send lists only when its `class` equals an existing `classId` **and** that class's `group` matches the active group (M/T). Students with `class=null` (or a class not in `classes/`) show in the **무소속(unassigned)** tab. `scores/` is read-only.

`testKey` format: `"{YYYY-MM-DD}|{type}|{round}"`. Exam dropdown is sorted by key descending (most recent first).

The DB at `dbPath` may be **shared** with other apps (e.g. DailyReportWizard owns `obs/`, `config/`, `session/`, `input/`, `lastSent/`). Never overwrite the whole `{dbPath}` node — write only `students/` and `classes/`.
