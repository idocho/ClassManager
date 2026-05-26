"""
app.py — KakaoAdmin 메인 GUI
Crafted by IDO(idocho@kakao.com) · Powered by Claude AI
"""
import json
import os
import sys
import tkinter as tk
from tkinter import messagebox, simpledialog, ttk
import urllib.parse

from firebase import firebase_get
from kakao_send import AUTOMATION, send_messages
from template_engine import build_common_ctx, build_score_ctx, list_variables, render

# ── 상수 ──────────────────────────────────────────────────────────────
_SYS   = sys.platform
_FONT  = ("맑은 고딕" if _SYS == "win32" else
          "Apple SD Gothic Neo" if _SYS == "darwin" else "sans-serif")
BG      = "#F5F6FA"
PANEL   = "#FFFFFF"
DARK    = "#1A1D2E"
ACCENT  = "#FEE500"
INDIGO  = "#4338CA"
GREEN   = "#22C55E"
GRAY    = "#94A3B8"
BORDER  = "#E2E8F0"
TEXT    = "#1E293B"
SUBTEXT = "#64748B"
RED     = "#EF4444"

FT = (_FONT, 10, "bold")
FB = (_FONT, 9)
FS = (_FONT, 8)

SETTINGS_PATH  = os.path.join(os.path.dirname(__file__), "settings.json")
TEMPLATES_PATH = os.path.join(os.path.dirname(__file__), "templates.json")


# ── 설정 I/O ──────────────────────────────────────────────────────────
def load_settings() -> dict:
    if os.path.exists(SETTINGS_PATH):
        with open(SETTINGS_PATH, encoding="utf-8") as f:
            return json.load(f)
    return {"firebase_url": "", "firebase_path": "", "wait_time": 0.5, "room_prefix": "오직 "}


def save_settings(cfg: dict):
    with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


def load_templates() -> list:
    if os.path.exists(TEMPLATES_PATH):
        with open(TEMPLATES_PATH, encoding="utf-8") as f:
            return json.load(f)
    return []


def save_templates(templates: list):
    with open(TEMPLATES_PATH, "w", encoding="utf-8") as f:
        json.dump(templates, f, ensure_ascii=False, indent=2)


# ── 메인 앱 ───────────────────────────────────────────────────────────
class KakaoAdminApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("KakaoTalk Blaster — 일괄 메시지 전송")
        self.root.configure(bg=BG)
        self.root.geometry("900x640")
        self.root.minsize(800, 560)

        self.cfg       = load_settings()
        self.templates = load_templates()

        # Firebase 로드 데이터
        self.fb_config  = {}   # config/ 전체
        self.fb_scores  = {}   # scores/{sheet}|{cls}/

        # 선택 상태
        self.cur_sheet    = tk.StringVar(value="M")
        self.cur_cls      = tk.StringVar(value="")
        self.student_vars = {}   # name → BooleanVar
        self.tmpl_idx     = -1

        self._build_ui()
        self.root.after(100, self._try_load_firebase)

    # ── UI 구성 ───────────────────────────────────────────────────────
    def _build_ui(self):
        self._build_topbar()
        body = tk.Frame(self.root, bg=BG)
        body.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        body.columnconfigure(0, weight=0, minsize=220)
        body.columnconfigure(1, weight=1)
        body.rowconfigure(0, weight=1)

        self._build_left(body)
        self._build_right(body)
        self._build_statusbar()

    def _build_topbar(self):
        bar = tk.Frame(self.root, bg=DARK, height=48)
        bar.pack(fill="x")
        bar.pack_propagate(False)

        tk.Label(bar, text="KakaoAdmin", font=(_FONT, 12, "bold"),
                 bg=DARK, fg=ACCENT).pack(side="left", padx=16, pady=10)
        tk.Label(bar, text="일괄 메시지 전송 — Admin Only",
                 font=FS, bg=DARK, fg=GRAY).pack(side="left", pady=10)

        # Firebase 연결 설정 버튼
        tk.Button(bar, text="⚙ 설정", font=FS, bg=DARK, fg=ACCENT,
                  relief="flat", cursor="hand2",
                  command=self._open_settings).pack(side="right", padx=12)

        if not AUTOMATION:
            tk.Label(bar, text="⚠ pyautogui 미설치", font=FS,
                     bg=RED, fg="white").pack(side="right", padx=8)

    def _build_left(self, parent):
        frm = tk.Frame(parent, bg=PANEL, bd=1, relief="flat",
                       highlightbackground=BORDER, highlightthickness=1)
        frm.grid(row=0, column=0, sticky="nsew", padx=(0, 8), pady=4)
        frm.rowconfigure(2, weight=1)

        # 시트 선택
        sh_frm = tk.Frame(frm, bg=PANEL)
        sh_frm.pack(fill="x", padx=10, pady=(10, 4))
        tk.Label(sh_frm, text="시트", font=FS, bg=PANEL, fg=SUBTEXT).pack(side="left")
        for s in ("M", "T"):
            tk.Radiobutton(sh_frm, text=s, variable=self.cur_sheet, value=s,
                           bg=PANEL, fg=TEXT, font=FB, selectcolor=PANEL,
                           command=self._on_sheet_change).pack(side="left", padx=6)

        # 반 선택
        cls_frm = tk.Frame(frm, bg=PANEL)
        cls_frm.pack(fill="x", padx=10, pady=(0, 6))
        tk.Label(cls_frm, text="반", font=FS, bg=PANEL, fg=SUBTEXT).pack(side="left")
        self.cls_cb = ttk.Combobox(cls_frm, textvariable=self.cur_cls,
                                   state="readonly", width=14, font=FB)
        self.cls_cb.pack(side="left", padx=6)
        self.cls_cb.bind("<<ComboboxSelected>>", lambda e: self._on_cls_change())

        tk.Button(cls_frm, text="↺", font=FS, bg=PANEL, fg=INDIGO,
                  relief="flat", cursor="hand2",
                  command=self._try_load_firebase).pack(side="left")

        # 학생 목록 헤더
        hdr = tk.Frame(frm, bg=PANEL)
        hdr.pack(fill="x", padx=10)
        tk.Label(hdr, text="학생 목록", font=FT, bg=PANEL, fg=TEXT).pack(side="left")
        tk.Button(hdr, text="전체선택", font=FS, bg=PANEL, fg=INDIGO,
                  relief="flat", cursor="hand2",
                  command=lambda: self._select_all(True)).pack(side="right")
        tk.Button(hdr, text="해제", font=FS, bg=PANEL, fg=GRAY,
                  relief="flat", cursor="hand2",
                  command=lambda: self._select_all(False)).pack(side="right", padx=4)

        # 학생 스크롤 리스트
        sc_frm = tk.Frame(frm, bg=PANEL)
        sc_frm.pack(fill="both", expand=True, padx=6, pady=4)
        sc_frm.rowconfigure(0, weight=1)
        sc_frm.columnconfigure(0, weight=1)

        self.student_canvas = tk.Canvas(sc_frm, bg=PANEL, highlightthickness=0)
        sb = tk.Scrollbar(sc_frm, orient="vertical",
                          command=self.student_canvas.yview)
        self.student_canvas.configure(yscrollcommand=sb.set)
        self.student_canvas.grid(row=0, column=0, sticky="nsew")
        sb.grid(row=0, column=1, sticky="ns")

        self.student_frame = tk.Frame(self.student_canvas, bg=PANEL)
        self.student_canvas.create_window((0, 0), window=self.student_frame,
                                          anchor="nw", tags="inner")
        self.student_frame.bind("<Configure>",
            lambda e: self.student_canvas.configure(
                scrollregion=self.student_canvas.bbox("all")))

        # 선택 카운트
        self.sel_label = tk.Label(frm, text="0명 선택", font=FS,
                                  bg=PANEL, fg=SUBTEXT)
        self.sel_label.pack(pady=(0, 8))

    def _build_right(self, parent):
        frm = tk.Frame(parent, bg=PANEL, bd=1, relief="flat",
                       highlightbackground=BORDER, highlightthickness=1)
        frm.grid(row=0, column=1, sticky="nsew", pady=4)
        frm.rowconfigure(3, weight=1)
        frm.columnconfigure(0, weight=1)

        # ── 템플릿 관리 ──
        tmpl_hdr = tk.Frame(frm, bg=PANEL)
        tmpl_hdr.grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 4))
        tk.Label(tmpl_hdr, text="메시지 템플릿", font=FT,
                 bg=PANEL, fg=TEXT).pack(side="left")
        tk.Button(tmpl_hdr, text="+ 추가", font=FS, bg=INDIGO, fg="white",
                  relief="flat", cursor="hand2", padx=6,
                  command=self._add_template).pack(side="right")
        tk.Button(tmpl_hdr, text="삭제", font=FS, bg=PANEL, fg=RED,
                  relief="flat", cursor="hand2",
                  command=self._del_template).pack(side="right", padx=4)

        # 템플릿 드롭다운 + 타입 표시
        tmpl_sel = tk.Frame(frm, bg=PANEL)
        tmpl_sel.grid(row=1, column=0, sticky="ew", padx=12, pady=(0, 6))

        self.tmpl_var = tk.StringVar()
        self.tmpl_cb  = ttk.Combobox(tmpl_sel, textvariable=self.tmpl_var,
                                     state="readonly", width=22, font=FB)
        self.tmpl_cb.pack(side="left")
        self.tmpl_cb.bind("<<ComboboxSelected>>", lambda e: self._on_tmpl_change())

        self.tmpl_type_lbl = tk.Label(tmpl_sel, text="", font=FS,
                                      bg=PANEL, fg=SUBTEXT)
        self.tmpl_type_lbl.pack(side="left", padx=10)

        # 성적 참조 — 시험 선택 (type=score 일 때만 활성)
        score_frm = tk.Frame(frm, bg=PANEL)
        score_frm.grid(row=2, column=0, sticky="ew", padx=12, pady=(0, 6))
        tk.Label(score_frm, text="성적 참조:", font=FS,
                 bg=PANEL, fg=SUBTEXT).pack(side="left")
        self.score_var = tk.StringVar()
        self.score_cb  = ttk.Combobox(score_frm, textvariable=self.score_var,
                                      state="readonly", width=26, font=FB)
        self.score_cb.pack(side="left", padx=6)
        self.score_cb.bind("<<ComboboxSelected>>", lambda e: self._update_preview())

        # 템플릿 에디터
        tk.Label(frm, text="템플릿 편집", font=FS, bg=PANEL, fg=SUBTEXT
                 ).grid(row=3, column=0, sticky="w", padx=12)
        self.tmpl_text = tk.Text(frm, font=FB, bg=PANEL, fg=TEXT,
                                 relief="flat", wrap="word",
                                 highlightbackground=BORDER,
                                 highlightthickness=1,
                                 insertbackground=TEXT)
        self.tmpl_text.grid(row=3, column=0, sticky="nsew",
                            padx=12, pady=(2, 4))
        self.tmpl_text.bind("<KeyRelease>", lambda e: self._on_tmpl_edit())

        # 변수 힌트
        hint_frm = tk.Frame(frm, bg=PANEL)
        hint_frm.grid(row=4, column=0, sticky="ew", padx=12, pady=(0, 4))
        tk.Label(hint_frm, text="변수:", font=FS, bg=PANEL,
                 fg=SUBTEXT).pack(side="left")
        for var, desc in list_variables():
            btn = tk.Button(hint_frm, text=var, font=FS, bg="#EEF2FF",
                            fg=INDIGO, relief="flat", cursor="hand2", padx=3,
                            command=lambda v=var: self._insert_var(v))
            btn.pack(side="left", padx=1)

        # 미리보기
        prev_frm = tk.Frame(frm, bg="#EEF2FF")
        prev_frm.grid(row=5, column=0, sticky="ew", padx=12, pady=(0, 8))
        tk.Label(prev_frm, text="미리보기 (첫 번째 학생)", font=FS,
                 bg="#EEF2FF", fg=INDIGO).pack(anchor="w", padx=6, pady=(4, 0))
        self.preview_lbl = tk.Label(prev_frm, text="", font=FS,
                                    bg="#EEF2FF", fg=TEXT,
                                    justify="left", anchor="w", wraplength=480)
        self.preview_lbl.pack(fill="x", padx=6, pady=(0, 6))

        # 전송 버튼
        send_frm = tk.Frame(frm, bg=PANEL)
        send_frm.grid(row=6, column=0, sticky="ew", padx=12, pady=(0, 12))
        self.send_btn = tk.Button(send_frm, text="카카오톡 창 활성화 후 전송",
                                  font=FT, bg=ACCENT, fg=DARK,
                                  relief="flat", cursor="hand2", pady=8,
                                  command=self._send)
        self.send_btn.pack(fill="x")

        self._refresh_template_cb()

    def _build_statusbar(self):
        self.status_bar = tk.Label(self.root, text="준비", font=FS,
                                   bg=DARK, fg=GRAY, anchor="w", padx=10)
        self.status_bar.pack(fill="x", side="bottom")

    def _set_status(self, text, color=None):
        self.status_bar.config(text=text, fg=color or GRAY)

    # ── Firebase 로드 ─────────────────────────────────────────────────
    def _try_load_firebase(self):
        url  = self.cfg.get("firebase_url", "")
        path = self.cfg.get("firebase_path", "")
        if not url or not path:
            self._set_status("Firebase 설정 없음 — ⚙ 설정에서 URL/Path 입력", RED)
            return
        self._set_status("Firebase 로드 중...", GRAY)
        import threading
        threading.Thread(target=self._load_fb_data, daemon=True).start()

    def _load_fb_data(self):
        try:
            data = firebase_get(self.cfg, "config")
            self.fb_config = data if isinstance(data, dict) else {}
            self.root.after(0, self._on_fb_loaded)
        except Exception as e:
            self.root.after(0, lambda: self._set_status(f"Firebase 오류: {e}", RED))

    def _on_fb_loaded(self):
        self._set_status("Firebase 연결 완료", GREEN)
        self._on_sheet_change()

    def _on_sheet_change(self):
        sheet = self.cur_sheet.get()
        classes = (self.fb_config
                   .get("sheets", {})
                   .get(sheet, {})
                   .get("classes", {})
                   .keys())
        cls_list = sorted(classes)
        self.cls_cb["values"] = cls_list
        if cls_list:
            self.cur_cls.set(cls_list[0])
            self._on_cls_change()
        else:
            self.cur_cls.set("")
            self._render_students([])

    def _on_cls_change(self):
        sheet = self.cur_sheet.get()
        cls   = self.cur_cls.get()
        if not cls:
            return
        students = (self.fb_config
                    .get("sheets", {})
                    .get(sheet, {})
                    .get("classes", {})
                    .get(cls, {})
                    .get("students", []))
        self._render_students(students)
        self._load_scores()

    def _load_scores(self):
        """현재 반의 scores/ 노드 로드."""
        sheet = self.cur_sheet.get()
        cls   = self.cur_cls.get()
        if not cls:
            return
        self.fb_scores = {}
        import threading
        def _fetch():
            try:
                data = firebase_get(self.cfg, f"scores/{sheet}|{cls}")
                self.fb_scores = data if isinstance(data, dict) else {}
            except Exception:
                self.fb_scores = {}
            self.root.after(0, self._refresh_score_cb)
        threading.Thread(target=_fetch, daemon=True).start()

    def _refresh_score_cb(self):
        items = []
        for k, v in sorted(self.fb_scores.items(), reverse=True):
            label = f"{v.get('date','')} {v.get('type','')} {v.get('round','')}".strip()
            items.append((k, label))
        self._score_items = items
        self.score_cb["values"] = [lbl for _, lbl in items]
        if items:
            self.score_var.set(items[0][1])
        else:
            self.score_var.set("")
        self._update_preview()

    def _get_selected_test_key(self):
        sel = self.score_var.get()
        for k, lbl in getattr(self, "_score_items", []):
            if lbl == sel:
                return k
        return None

    # ── 학생 목록 렌더 ───────────────────────────────────────────────
    def _render_students(self, students):
        for w in self.student_frame.winfo_children():
            w.destroy()
        self.student_vars.clear()

        for s in students:
            name = s.get("name", "")
            var  = tk.BooleanVar(value=True)
            self.student_vars[name] = var
            cb = tk.Checkbutton(self.student_frame, text=name,
                                variable=var, font=FB,
                                bg=PANEL, fg=TEXT,
                                selectcolor=PANEL, anchor="w",
                                command=self._update_sel_count)
            cb.pack(fill="x", padx=8, pady=1)

        self._update_sel_count()
        self._update_preview()

    def _select_all(self, val: bool):
        for v in self.student_vars.values():
            v.set(val)
        self._update_sel_count()
        self._update_preview()

    def _update_sel_count(self):
        n = sum(1 for v in self.student_vars.values() if v.get())
        self.sel_label.config(text=f"{n}명 선택")

    # ── 템플릿 관리 ──────────────────────────────────────────────────
    def _refresh_template_cb(self):
        names = [t["name"] for t in self.templates]
        self.tmpl_cb["values"] = names
        if names:
            if self.tmpl_idx < 0 or self.tmpl_idx >= len(names):
                self.tmpl_idx = 0
            self.tmpl_var.set(names[self.tmpl_idx])
            self._load_tmpl(self.tmpl_idx)
        else:
            self.tmpl_var.set("")
            self.tmpl_text.delete("1.0", "end")

    def _on_tmpl_change(self):
        sel = self.tmpl_var.get()
        for i, t in enumerate(self.templates):
            if t["name"] == sel:
                self.tmpl_idx = i
                self._load_tmpl(i)
                break

    def _load_tmpl(self, idx):
        t = self.templates[idx]
        self.tmpl_text.delete("1.0", "end")
        self.tmpl_text.insert("1.0", t.get("body", ""))
        ttype = t.get("type", "common")
        self.tmpl_type_lbl.config(
            text="[성적 참조]" if ttype == "score" else "[일반]",
            fg=INDIGO if ttype == "score" else SUBTEXT)
        # score 타입이면 score_cb 활성
        state = "readonly" if ttype == "score" else "disabled"
        self.score_cb.config(state=state)
        self._update_preview()

    def _on_tmpl_edit(self):
        if 0 <= self.tmpl_idx < len(self.templates):
            self.templates[self.tmpl_idx]["body"] = self.tmpl_text.get("1.0", "end-1c")
            save_templates(self.templates)
        self._update_preview()

    def _add_template(self):
        name = simpledialog.askstring("템플릿 추가", "템플릿 이름:",
                                      parent=self.root)
        if not name:
            return
        ttype = messagebox.askquestion("유형 선택",
            "성적 참조 템플릿입니까?\n(예=성적참조 / 아니오=일반)",
            parent=self.root)
        tmpl = {
            "name": name,
            "type": "score" if ttype == "yes" else "common",
            "body": "",
        }
        self.templates.append(tmpl)
        self.tmpl_idx = len(self.templates) - 1
        save_templates(self.templates)
        self._refresh_template_cb()

    def _del_template(self):
        if not self.templates or self.tmpl_idx < 0:
            return
        name = self.templates[self.tmpl_idx]["name"]
        if not messagebox.askyesno("삭제 확인", f'"{name}" 삭제?', parent=self.root):
            return
        self.templates.pop(self.tmpl_idx)
        self.tmpl_idx = max(0, self.tmpl_idx - 1)
        save_templates(self.templates)
        self._refresh_template_cb()

    def _insert_var(self, var: str):
        self.tmpl_text.insert("insert", var)
        self._on_tmpl_edit()

    # ── 미리보기 ─────────────────────────────────────────────────────
    def _update_preview(self):
        selected = [n for n, v in self.student_vars.items() if v.get()]
        if not selected:
            self.preview_lbl.config(text="(선택된 학생 없음)")
            return
        name = selected[0]
        cls  = self.cur_cls.get()
        body = self.tmpl_text.get("1.0", "end-1c") if self.tmpl_text.winfo_exists() else ""
        try:
            if (0 <= self.tmpl_idx < len(self.templates) and
                    self.templates[self.tmpl_idx].get("type") == "score"):
                test_key = self._get_selected_test_key()
                test_data = self.fb_scores.get(test_key, {}) if test_key else {}
                ctx = build_score_ctx(name, cls, test_data)
            else:
                ctx = build_common_ctx(name, cls)
            self.preview_lbl.config(text=render(body, ctx))
        except Exception as e:
            self.preview_lbl.config(text=f"[오류] {e}")

    # ── 전송 ─────────────────────────────────────────────────────────
    def _send(self):
        if not AUTOMATION:
            messagebox.showerror("오류",
                "pyautogui / pyperclip이 설치되어 있지 않습니다.\n"
                "pip install pyautogui pyperclip")
            return

        selected = [n for n, v in self.student_vars.items() if v.get()]
        if not selected:
            messagebox.showinfo("알림", "전송 대상 학생을 선택하세요.")
            return

        cls  = self.cur_cls.get()
        body = self.tmpl_text.get("1.0", "end-1c")
        prefix = self.cfg.get("room_prefix", "오직 ")
        is_score = (0 <= self.tmpl_idx < len(self.templates) and
                    self.templates[self.tmpl_idx].get("type") == "score")

        test_key  = self._get_selected_test_key() if is_score else None
        test_data = self.fb_scores.get(test_key, {}) if test_key else {}

        # 성적 참조 시 점수 없는 학생 제외
        if is_score:
            score_map = test_data.get("students", {})
            no_score  = [n for n in selected if n not in score_map]
            selected  = [n for n in selected if n in score_map]
            if no_score:
                messagebox.showinfo("안내",
                    f"점수 없는 학생 {len(no_score)}명 제외:\n" + ", ".join(no_score))
            if not selected:
                messagebox.showinfo("알림", "전송 가능한 학생이 없습니다.")
                return

        msgs = []
        for name in selected:
            if is_score:
                ctx = build_score_ctx(name, cls, test_data)
            else:
                ctx = build_common_ctx(name, cls)
            msgs.append({
                "room": f"{prefix}{name}",
                "msg":  render(body, ctx),
            })

        confirm = (f"전송 대상: {len(msgs)}명\n" +
                   ", ".join(m["room"] for m in msgs) +
                   "\n\n카카오톡 창 활성화 후 [예]를 누르세요. (3초 후 시작)")
        if not messagebox.askyesno("전송 확인", confirm):
            return

        self.send_btn.config(state="disabled")
        wait = self.cfg.get("wait_time", 0.5)

        def _status(text):
            self.root.after(0, lambda: self._set_status(text))

        def _done(total):
            def _ui():
                self._set_status(f"✅ 전송 완료 — {total}명", GREEN)
                self.send_btn.config(state="normal")
                messagebox.showinfo("완료", f"{total}명 전송 완료!")
            self.root.after(0, _ui)

        send_messages(msgs, wait_time=wait, status_cb=_status, done_cb=_done)

    # ── 설정 다이얼로그 ──────────────────────────────────────────────
    def _open_settings(self):
        dlg = tk.Toplevel(self.root)
        dlg.title("설정")
        dlg.configure(bg=BG)
        dlg.geometry("480x280")
        dlg.grab_set()

        fields = [
            ("Firebase URL",   "firebase_url"),
            ("Firebase Path",  "firebase_path"),
            ("카톡 채팅방 접두사", "room_prefix"),
            ("전송 딜레이(초)",  "wait_time"),
        ]
        vars_ = {}
        for i, (label, key) in enumerate(fields):
            tk.Label(dlg, text=label, font=FB, bg=BG, fg=TEXT,
                     anchor="w").grid(row=i, column=0, sticky="w",
                                      padx=16, pady=8)
            v = tk.StringVar(value=str(self.cfg.get(key, "")))
            vars_[key] = v
            tk.Entry(dlg, textvariable=v, font=FB, width=36,
                     relief="flat", bg=PANEL,
                     highlightbackground=BORDER,
                     highlightthickness=1).grid(row=i, column=1,
                                                padx=8, pady=8, sticky="ew")
        dlg.columnconfigure(1, weight=1)

        def _save():
            for key, v in vars_.items():
                val = v.get().strip()
                if key == "wait_time":
                    try:
                        self.cfg[key] = float(val)
                    except ValueError:
                        self.cfg[key] = 0.5
                else:
                    self.cfg[key] = val
            save_settings(self.cfg)
            dlg.destroy()
            self._try_load_firebase()

        tk.Button(dlg, text="저장 & 재연결", font=FT, bg=ACCENT, fg=DARK,
                  relief="flat", cursor="hand2", pady=6,
                  command=_save).grid(row=len(fields), column=0,
                                      columnspan=2, padx=16, pady=12, sticky="ew")
