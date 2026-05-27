"""
app.py — ClassManager 메인 GUI
Crafted by IDO(idocho@kakao.com) · Powered by Claude AI
"""
import json
import os
import sys
import threading
import tkinter as tk
from tkinter import messagebox, simpledialog, ttk
import urllib.parse

from firebase import firebase_delete, firebase_get, firebase_patch, firebase_put
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

if getattr(sys, "frozen", False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(__file__)

SETTINGS_PATH  = os.path.join(BASE_DIR, "settings.json")
TEMPLATES_PATH = os.path.join(BASE_DIR, "templates.json")


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
class ClassManagerApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("ClassManager")
        self.root.configure(bg=BG)
        self.root.geometry("960x680")
        self.root.minsize(840, 580)

        self.cfg       = load_settings()
        self.templates = load_templates()

        # Firebase 로드 데이터
        self.fb_config = {}
        self.fb_scores = {}

        # 명단 탭 상태
        self.roster_sheet    = tk.StringVar(value="M")
        self._roster_cls     = ""
        self._roster_sel_stu = []

        # 발송 탭 상태
        self.cur_sheet       = tk.StringVar(value="M")
        self.cur_cls         = tk.StringVar(value="")
        self.student_vars    = {}
        self.send_selections = {}   # {sheet: {cls: {name: BooleanVar}}}
        self.tmpl_idx        = -1

        self._build_ui()
        self.root.after(100, self._try_load_firebase)

    # ── UI 구성 ───────────────────────────────────────────────────────
    def _build_ui(self):
        self._build_topbar()
        self._build_statusbar()

        self.nb = ttk.Notebook(self.root)
        self.nb.pack(fill="both", expand=True, padx=10, pady=(4, 10))

        self._build_roster_tab()
        self._build_send_tab()
        self._build_settings_tab()

    def _build_topbar(self):
        bar = tk.Frame(self.root, bg=DARK, height=48)
        bar.pack(fill="x")
        bar.pack_propagate(False)

        tk.Label(bar, text="ClassManager", font=(_FONT, 12, "bold"),
                 bg=DARK, fg=ACCENT).pack(side="left", padx=16, pady=10)
        tk.Label(bar, text="학원 관리 · 메시지 발송",
                 font=FS, bg=DARK, fg=GRAY).pack(side="left", pady=10)

        if not AUTOMATION:
            tk.Label(bar, text="⚠ pyautogui 미설치", font=FS,
                     bg=RED, fg="white").pack(side="right", padx=8)

    def _build_statusbar(self):
        self.status_bar = tk.Label(self.root, text="준비", font=FS,
                                   bg=DARK, fg=GRAY, anchor="w", padx=10)
        self.status_bar.pack(fill="x", side="bottom")

    def _set_status(self, text, color=None):
        self.status_bar.config(text=text, fg=color or GRAY)

    # ══════════════════════════════════════════════════════════════════
    # TAB 1 — 명단 관리
    # ══════════════════════════════════════════════════════════════════
    def _build_roster_tab(self):
        tab = tk.Frame(self.nb, bg=BG)
        self.nb.add(tab, text="  명단 관리  ")
        tab.columnconfigure(0, weight=0, minsize=240)
        tab.columnconfigure(1, weight=1)
        tab.rowconfigure(0, weight=1)
        self._build_roster_left(tab)
        self._build_roster_right(tab)

        # Export / Import 툴바
        bar = tk.Frame(tab, bg=BG)
        bar.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(4, 0))
        tk.Button(bar, text="⬆ Import CSV", font=FS, bg=PANEL, fg=INDIGO,
                  relief="flat", cursor="hand2",
                  command=self._import_csv).pack(side="left", padx=4)
        tk.Button(bar, text="⬇ Export CSV", font=FS, bg=PANEL, fg=SUBTEXT,
                  relief="flat", cursor="hand2",
                  command=self._export_csv).pack(side="left")

    def _build_roster_left(self, parent):
        frm = tk.Frame(parent, bg=PANEL,
                       highlightbackground=BORDER, highlightthickness=1)
        frm.grid(row=0, column=0, sticky="nsew", padx=(0, 8), pady=4)
        frm.rowconfigure(2, weight=1)

        # 시트 선택
        sh_frm = tk.Frame(frm, bg=PANEL)
        sh_frm.pack(fill="x", padx=10, pady=(10, 4))
        tk.Label(sh_frm, text="시트", font=FS, bg=PANEL, fg=SUBTEXT).pack(side="left")
        for s in ("M", "T"):
            tk.Radiobutton(sh_frm, text=s, variable=self.roster_sheet, value=s,
                           bg=PANEL, fg=TEXT, font=FB, selectcolor=PANEL,
                           command=self._on_roster_sheet_change).pack(side="left", padx=6)

        # 반 목록 헤더
        hdr = tk.Frame(frm, bg=PANEL)
        hdr.pack(fill="x", padx=10, pady=(4, 2))
        tk.Label(hdr, text="반 목록", font=FT, bg=PANEL, fg=TEXT).pack(side="left")

        # 반 Listbox
        lb_frm = tk.Frame(frm, bg=PANEL)
        lb_frm.pack(fill="both", expand=True, padx=8, pady=4)
        lb_frm.rowconfigure(0, weight=1)
        lb_frm.columnconfigure(0, weight=1)

        self.cls_listbox = tk.Listbox(
            lb_frm, font=FB, bg=PANEL, fg=TEXT,
            selectbackground=INDIGO, selectforeground="white",
            relief="flat", highlightbackground=BORDER, highlightthickness=1,
            activestyle="none")
        sb = tk.Scrollbar(lb_frm, orient="vertical", command=self.cls_listbox.yview)
        self.cls_listbox.configure(yscrollcommand=sb.set)
        self.cls_listbox.grid(row=0, column=0, sticky="nsew")
        sb.grid(row=0, column=1, sticky="ns")
        self.cls_listbox.bind("<<ListboxSelect>>", lambda e: self._on_roster_cls_select())

        # 반 관리 버튼
        btn_frm = tk.Frame(frm, bg=PANEL)
        btn_frm.pack(fill="x", padx=8, pady=(0, 8))
        for text, cmd, fg in [
            ("+ 반 추가",  self._roster_add_class,    INDIGO),
            ("이름 변경",  self._roster_rename_class,  SUBTEXT),
            ("반 삭제",    self._roster_del_class,     RED),
        ]:
            tk.Button(btn_frm, text=text, font=FS, bg=PANEL, fg=fg,
                      relief="flat", cursor="hand2",
                      command=cmd).pack(side="left", padx=2)

    def _build_roster_right(self, parent):
        frm = tk.Frame(parent, bg=PANEL,
                       highlightbackground=BORDER, highlightthickness=1)
        frm.grid(row=0, column=1, sticky="nsew", pady=4)
        frm.rowconfigure(1, weight=1)
        frm.columnconfigure(0, weight=1)

        # 반 이름 헤더
        self.roster_cls_lbl = tk.Label(frm, text="반을 선택하세요", font=FT,
                                       bg=PANEL, fg=TEXT, anchor="w")
        self.roster_cls_lbl.grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 4))

        # 학생 Listbox
        lb_frm = tk.Frame(frm, bg=PANEL)
        lb_frm.grid(row=1, column=0, sticky="nsew", padx=8, pady=4)
        lb_frm.rowconfigure(0, weight=1)
        lb_frm.columnconfigure(0, weight=1)

        self.student_listbox = tk.Listbox(
            lb_frm, font=FB, bg=PANEL, fg=TEXT,
            selectbackground=INDIGO, selectforeground="white",
            relief="flat", highlightbackground=BORDER, highlightthickness=1,
            activestyle="none", selectmode="extended")
        sb2 = tk.Scrollbar(lb_frm, orient="vertical", command=self.student_listbox.yview)
        self.student_listbox.configure(yscrollcommand=sb2.set)
        self.student_listbox.grid(row=0, column=0, sticky="nsew")
        sb2.grid(row=0, column=1, sticky="ns")
        self.student_listbox.bind("<Control-Button-1>", self._on_student_ctrl_click)

        # 학생 관리 버튼
        btn_frm = tk.Frame(frm, bg=PANEL)
        btn_frm.grid(row=2, column=0, sticky="ew", padx=8, pady=(0, 8))
        for text, cmd, fg in [
            ("+ 학생 추가",    self._roster_add_student,   INDIGO),
            ("다른 반으로 이관", self._roster_move_student,  SUBTEXT),
            ("학생 제거",      self._roster_del_student,   RED),
        ]:
            tk.Button(btn_frm, text=text, font=FS, bg=PANEL, fg=fg,
                      relief="flat", cursor="hand2",
                      command=cmd).pack(side="left", padx=2)

        self.roster_count_lbl = tk.Label(frm, text="", font=FS, bg=PANEL, fg=SUBTEXT)
        self.roster_count_lbl.grid(row=3, column=0, sticky="w", padx=12, pady=(0, 8))

    # ── 명단 탭 이벤트 ────────────────────────────────────────────────
    def _on_roster_sheet_change(self):
        sheet = self.roster_sheet.get()
        classes = sorted(
            self.fb_config.get("sheets", {})
                          .get(sheet, {})
                          .get("classes", {})
                          .keys()
        )
        self.cls_listbox.delete(0, "end")
        for c in classes:
            self.cls_listbox.insert("end", c)
        self.student_listbox.delete(0, "end")
        self.roster_cls_lbl.config(text="반을 선택하세요")
        self.roster_count_lbl.config(text="")

    def _on_roster_cls_select(self):
        sel = self.cls_listbox.curselection()
        if not sel:
            return
        cls   = self.cls_listbox.get(sel[0])
        self._roster_cls = cls
        sheet = self.roster_sheet.get()
        students = (self.fb_config
                    .get("sheets", {})
                    .get(sheet, {})
                    .get("classes", {})
                    .get(cls, {})
                    .get("students", []))
        self.roster_cls_lbl.config(text=f"{cls}  ({sheet}반)")
        self.student_listbox.delete(0, "end")
        for name in sorted(s.get("name", "") for s in students):
            self.student_listbox.insert("end", name)
        self.roster_count_lbl.config(text=f"총 {len(students)}명")
        self._roster_sel_stu = []

    def _get_roster_cls(self):
        if not self._roster_cls:
            messagebox.showinfo("알림", "반을 먼저 선택하세요.", parent=self.root)
            return None
        return self._roster_cls

    def _on_student_ctrl_click(self, event):
        idx = self.student_listbox.nearest(event.y)
        if idx < 0:
            return "break"
        if idx in self.student_listbox.curselection():
            self.student_listbox.selection_clear(idx)
        else:
            self.student_listbox.selection_set(idx)
        self._roster_sel_stu = [self.student_listbox.get(i)
                                for i in self.student_listbox.curselection()]
        return "break"

    def _get_selected_students(self):
        # curselection 우선, 포커스 잃었으면 저장된 값 사용
        sel = self.student_listbox.curselection()
        if sel:
            self._roster_sel_stu = [self.student_listbox.get(i) for i in sel]
        return self._roster_sel_stu

    # ── 반 CRUD ───────────────────────────────────────────────────────
    def _roster_add_class(self):
        name = simpledialog.askstring("반 추가", "새 반 이름:", parent=self.root)
        if not name:
            return
        name  = name.strip()
        sheet = self.roster_sheet.get()
        (self.fb_config
             .setdefault("sheets", {})
             .setdefault(sheet, {})
             .setdefault("classes", {}))[name] = {"students": []}

        def _write():
            try:
                firebase_put(self.cfg,
                             f"config/sheets/{sheet}/classes/{name}/students", [])
                self.root.after(0, lambda: (
                    self._on_roster_sheet_change(),
                    self._set_status(f"반 '{name}' 추가 완료", GREEN)))
            except Exception as e:
                self.root.after(0, lambda: self._set_status(f"오류: {e}", RED))
        threading.Thread(target=_write, daemon=True).start()

    def _roster_del_class(self):
        cls = self._get_roster_cls()
        if not cls:
            return
        sheet = self.roster_sheet.get()
        if not messagebox.askyesno(
                "반 삭제",
                f"'{cls}' 반을 삭제합니까?\n소속 학생 정보도 함께 삭제됩니다.",
                parent=self.root):
            return
        self.fb_config.get("sheets", {}).get(sheet, {}).get("classes", {}).pop(cls, None)

        def _write():
            try:
                firebase_delete(self.cfg, f"config/sheets/{sheet}/classes/{cls}")
                self.root.after(0, lambda: (
                    self._on_roster_sheet_change(),
                    self._set_status(f"반 '{cls}' 삭제 완료", GREEN)))
            except Exception as e:
                self.root.after(0, lambda: self._set_status(f"오류: {e}", RED))
        threading.Thread(target=_write, daemon=True).start()

    def _roster_rename_class(self):
        cls = self._get_roster_cls()
        if not cls:
            return
        sheet    = self.roster_sheet.get()
        new_name = simpledialog.askstring("반 이름 변경", f"'{cls}' → 새 이름:",
                                          parent=self.root)
        if not new_name or new_name.strip() == cls:
            return
        new_name  = new_name.strip()
        classes   = self.fb_config.get("sheets", {}).get(sheet, {}).get("classes", {})
        cls_data  = classes.get(cls, {"students": []})
        classes[new_name] = cls_data
        classes.pop(cls, None)

        def _write():
            try:
                firebase_put(self.cfg,
                             f"config/sheets/{sheet}/classes/{new_name}", cls_data)
                firebase_delete(self.cfg, f"config/sheets/{sheet}/classes/{cls}")
                # scores 이관
                try:
                    scores = firebase_get(self.cfg, f"scores/{sheet}|{cls}")
                    if scores:
                        firebase_put(self.cfg, f"scores/{sheet}|{new_name}", scores)
                        firebase_delete(self.cfg, f"scores/{sheet}|{cls}")
                except Exception:
                    pass
                self.root.after(0, lambda: (
                    self._on_roster_sheet_change(),
                    self._set_status(f"'{cls}' → '{new_name}' 변경 완료", GREEN)))
            except Exception as e:
                self.root.after(0, lambda: self._set_status(f"오류: {e}", RED))
        threading.Thread(target=_write, daemon=True).start()

    # ── 학생 CRUD ─────────────────────────────────────────────────────
    def _roster_add_student(self):
        cls = self._get_roster_cls()
        if not cls:
            return
        sheet = self.roster_sheet.get()
        name  = simpledialog.askstring("학생 추가", "학생 이름:", parent=self.root)
        if not name:
            return
        name     = name.strip()
        students = (self.fb_config.get("sheets", {})
                                  .get(sheet, {})
                                  .get("classes", {})
                                  .get(cls, {})
                                  .get("students", []))
        if any(s.get("name") == name for s in students):
            messagebox.showinfo("알림", f"'{name}'은 이미 등록된 학생입니다.",
                                parent=self.root)
            return
        students.append({"name": name})

        def _write():
            try:
                firebase_put(self.cfg,
                             f"config/sheets/{sheet}/classes/{cls}/students", students)
                self.root.after(0, lambda: (
                    self._on_roster_cls_select(),
                    self._set_status(f"'{name}' 추가 완료", GREEN)))
            except Exception as e:
                self.root.after(0, lambda: self._set_status(f"오류: {e}", RED))
        threading.Thread(target=_write, daemon=True).start()

    def _roster_del_student(self):
        cls = self._get_roster_cls()
        if not cls:
            return
        selected = self._get_selected_students()
        if not selected:
            messagebox.showinfo("알림", "학생을 선택하세요.", parent=self.root)
            return
        sheet = self.roster_sheet.get()
        if not messagebox.askyesno(
                "학생 제거",
                f"{len(selected)}명을 '{cls}'에서 제거합니까?\n" + ", ".join(selected),
                parent=self.root):
            return
        students = (self.fb_config.get("sheets", {})
                                  .get(sheet, {})
                                  .get("classes", {})
                                  .get(cls, {})
                                  .get("students", []))
        students = [s for s in students if s.get("name") not in selected]
        self.fb_config["sheets"][sheet]["classes"][cls]["students"] = students

        def _write():
            try:
                firebase_put(self.cfg,
                             f"config/sheets/{sheet}/classes/{cls}/students", students)
                self.root.after(0, lambda: (
                    self._on_roster_cls_select(),
                    self._set_status(f"{len(selected)}명 제거 완료", GREEN)))
            except Exception as e:
                self.root.after(0, lambda: self._set_status(f"오류: {e}", RED))
        threading.Thread(target=_write, daemon=True).start()

    def _roster_move_student(self):
        cls = self._get_roster_cls()
        if not cls:
            return
        selected = self._get_selected_students()
        if not selected:
            messagebox.showinfo("알림", "학생을 선택하세요.", parent=self.root)
            return
        sheet = self.roster_sheet.get()

        dlg = tk.Toplevel(self.root)
        dlg.title("반 이관")
        dlg.configure(bg=BG)
        dlg.geometry("360x210")
        dlg.grab_set()

        tk.Label(dlg, text=f"{len(selected)}명 이관 — 대상 반 선택",
                 font=FB, bg=BG, fg=TEXT).pack(pady=(16, 8))

        row = tk.Frame(dlg, bg=BG)
        row.pack(pady=4)
        dst_sheet_var = tk.StringVar(value=sheet)
        for s in ("M", "T"):
            tk.Radiobutton(row, text=s, variable=dst_sheet_var, value=s,
                           bg=BG, fg=TEXT, font=FB,
                           selectcolor=BG).pack(side="left", padx=8)

        dst_cls_var = tk.StringVar()
        dst_cb = ttk.Combobox(dlg, textvariable=dst_cls_var,
                              state="readonly", width=22, font=FB)
        dst_cb.pack(pady=8)

        def _update_cls_list(*_):
            sh = dst_sheet_var.get()
            classes = sorted(
                self.fb_config.get("sheets", {}).get(sh, {}).get("classes", {}).keys())
            dst_cb["values"] = [c for c in classes if not (sh == sheet and c == cls)]
            dst_cls_var.set("")
        dst_sheet_var.trace_add("write", _update_cls_list)
        _update_cls_list()

        def _confirm():
            dst_cls = dst_cls_var.get()
            if not dst_cls:
                messagebox.showinfo("알림", "이관할 반을 선택하세요.", parent=dlg)
                return
            dst_sh = dst_sheet_var.get()
            dlg.destroy()
            self._do_move_students(selected, sheet, cls, dst_sh, dst_cls)

        tk.Button(dlg, text="이관", font=FT, bg=ACCENT, fg=DARK,
                  relief="flat", cursor="hand2", pady=6,
                  command=_confirm).pack(fill="x", padx=24, pady=8)

    def _do_move_students(self, names: list, src_sh: str, src_cls: str,
                          dst_sh: str, dst_cls: str):
        self._set_status(f"{len(names)}명 이관 중...", GRAY)

        def _worker():
            try:
                # 1. 소스 반에서 제거
                src_students = (self.fb_config.get("sheets", {})
                                              .get(src_sh, {})
                                              .get("classes", {})
                                              .get(src_cls, {})
                                              .get("students", []))
                new_src = [s for s in src_students if s.get("name") not in names]
                firebase_put(self.cfg,
                             f"config/sheets/{src_sh}/classes/{src_cls}/students",
                             new_src)

                # 2. 대상 반에 추가
                dst_students = (self.fb_config.get("sheets", {})
                                              .get(dst_sh, {})
                                              .get("classes", {})
                                              .get(dst_cls, {})
                                              .get("students", []))
                existing = {s.get("name") for s in dst_students}
                for name in names:
                    if name not in existing:
                        dst_students.append({"name": name})
                firebase_put(self.cfg,
                             f"config/sheets/{dst_sh}/classes/{dst_cls}/students",
                             dst_students)

                # 3. obs 이관
                for name in names:
                    src_key = urllib.parse.quote(f"{src_sh}|{src_cls}|{name}", safe="")
                    dst_key = urllib.parse.quote(f"{dst_sh}|{dst_cls}|{name}", safe="")
                    try:
                        obs = firebase_get(self.cfg, f"obs/{src_key}")
                        if obs:
                            firebase_put(self.cfg, f"obs/{dst_key}", obs)
                            firebase_delete(self.cfg, f"obs/{src_key}")
                    except Exception:
                        pass

                # 4. 로컬 업데이트
                self.fb_config["sheets"][src_sh]["classes"][src_cls]["students"] = new_src
                (self.fb_config
                     .setdefault("sheets", {})
                     .setdefault(dst_sh, {})
                     .setdefault("classes", {})
                     .setdefault(dst_cls, {}))["students"] = dst_students

                self.root.after(0, lambda: (
                    self._on_roster_sheet_change(),
                    self._set_status(
                        f"{len(names)}명 이관 완료 → {dst_sh}/{dst_cls}", GREEN)))
            except Exception as e:
                self.root.after(0, lambda: self._set_status(f"이관 오류: {e}", RED))

        threading.Thread(target=_worker, daemon=True).start()

    # ── Export / Import ───────────────────────────────────────────────
    def _export_csv(self):
        import csv
        from tkinter import filedialog
        path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV", "*.csv")],
            initialfile="roster.csv",
            parent=self.root)
        if not path:
            return
        sheets = self.fb_config.get("sheets", {})
        rows = []
        for sh in ("M", "T"):
            for cls, cls_data in sorted(sheets.get(sh, {}).get("classes", {}).items()):
                for s in sorted(cls_data.get("students", []),
                                key=lambda x: x.get("name", "")):
                    rows.append((sh, cls, s.get("name", "")))
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(["sheet", "class", "name"])
            w.writerows(rows)
        self._set_status(f"Export 완료 — {len(rows)}명 ({path})", GREEN)

    def _import_csv(self):
        import csv
        from tkinter import filedialog
        path = filedialog.askopenfilename(
            filetypes=[("CSV", "*.csv")],
            parent=self.root)
        if not path:
            return
        try:
            data = {}
            with open(path, newline="", encoding="utf-8-sig") as f:
                for row in csv.DictReader(f):
                    sh, cls, name = row["sheet"].strip(), row["class"].strip(), row["name"].strip()
                    if not (sh and cls and name):
                        continue
                    (data.setdefault(sh, {})
                         .setdefault(cls, [])
                         .append({"name": name}))
        except Exception as e:
            messagebox.showerror("오류", f"CSV 파싱 실패: {e}", parent=self.root)
            return

        total = sum(len(v) for cls_d in data.values() for v in cls_d.values())
        sheets_info = ", ".join(
            f"{sh} {len(cls_d)}반 {sum(len(v) for v in cls_d.values())}명"
            for sh, cls_d in sorted(data.items()))
        if not messagebox.askyesno(
                "Import 확인",
                f"기존 명단 전체를 덮어씁니다.\n\n{sheets_info}\n총 {total}명\n\n진행합니까?",
                parent=self.root):
            return

        payload = {
            sh: {"classes": {cls: {"students": students}
                             for cls, students in cls_d.items()}}
            for sh, cls_d in data.items()
        }

        def _upload():
            try:
                firebase_put(self.cfg, "config/sheets", payload)
                self.fb_config["sheets"] = {
                    sh: v["classes"] and {"classes": v["classes"]}
                    for sh, v in payload.items()
                }
                data2 = firebase_get(self.cfg, "config")
                self.fb_config = data2 if isinstance(data2, dict) else {}
                self.root.after(0, lambda: (
                    self._on_roster_sheet_change(),
                    self._set_status(f"Import 완료 — {total}명", GREEN)))
            except Exception as e:
                self.root.after(0, lambda: self._set_status(f"Import 오류: {e}", RED))

        threading.Thread(target=_upload, daemon=True).start()

    # ══════════════════════════════════════════════════════════════════
    # TAB 2 — 메시지 발송
    # ══════════════════════════════════════════════════════════════════
    def _build_send_tab(self):
        tab = tk.Frame(self.nb, bg=BG)
        self.nb.add(tab, text="  메시지 발송  ")
        tab.columnconfigure(0, weight=0, minsize=220)
        tab.columnconfigure(1, weight=1)
        tab.rowconfigure(0, weight=1)
        self._build_send_left(tab)
        self._build_send_right(tab)

    def _build_send_left(self, parent):
        frm = tk.Frame(parent, bg=PANEL,
                       highlightbackground=BORDER, highlightthickness=1)
        frm.grid(row=0, column=0, sticky="nsew", padx=(0, 8), pady=4)
        frm.rowconfigure(2, weight=1)

        sh_frm = tk.Frame(frm, bg=PANEL)
        sh_frm.pack(fill="x", padx=10, pady=(10, 4))
        tk.Label(sh_frm, text="시트", font=FS, bg=PANEL, fg=SUBTEXT).pack(side="left")
        for s in ("M", "T"):
            tk.Radiobutton(sh_frm, text=s, variable=self.cur_sheet, value=s,
                           bg=PANEL, fg=TEXT, font=FB, selectcolor=PANEL,
                           command=self._on_sheet_change).pack(side="left", padx=6)

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

        hdr = tk.Frame(frm, bg=PANEL)
        hdr.pack(fill="x", padx=10)
        tk.Label(hdr, text="학생 목록", font=FT, bg=PANEL, fg=TEXT).pack(side="left")
        tk.Button(hdr, text="전체선택", font=FS, bg=PANEL, fg=INDIGO,
                  relief="flat", cursor="hand2",
                  command=lambda: self._select_all(True)).pack(side="right")
        tk.Button(hdr, text="해제", font=FS, bg=PANEL, fg=GRAY,
                  relief="flat", cursor="hand2",
                  command=lambda: self._select_all(False)).pack(side="right", padx=4)

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

        sel_frm = tk.Frame(frm, bg=PANEL)
        sel_frm.pack(fill="x", padx=8, pady=(0, 8))
        self.sel_label = tk.Label(sel_frm, text="0명 선택", font=FS,
                                  bg=PANEL, fg=SUBTEXT)
        self.sel_label.pack(side="left")
        tk.Button(sel_frm, text="초기화", font=FS, bg=PANEL, fg=RED,
                  relief="flat", cursor="hand2",
                  command=self._clear_all_selections).pack(side="right")

    def _build_send_right(self, parent):
        frm = tk.Frame(parent, bg=PANEL,
                       highlightbackground=BORDER, highlightthickness=1)
        frm.grid(row=0, column=1, sticky="nsew", pady=4)
        frm.rowconfigure(3, weight=1)
        frm.columnconfigure(0, weight=1)

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

        self.score_frm = tk.Frame(frm, bg=PANEL)
        self.score_frm.grid(row=2, column=0, sticky="ew", padx=12, pady=(0, 6))
        self.score_frm.grid_remove()
        tk.Label(self.score_frm, text="성적 참조:", font=FS,
                 bg=PANEL, fg=SUBTEXT).pack(side="left")
        self.score_var = tk.StringVar()
        self.score_cb  = ttk.Combobox(self.score_frm, textvariable=self.score_var,
                                      state="readonly", width=26, font=FB)
        self.score_cb.pack(side="left", padx=6)
        self.score_cb.bind("<<ComboboxSelected>>", lambda e: self._update_preview())

        tk.Label(frm, text="템플릿 편집", font=FS, bg=PANEL,
                 fg=SUBTEXT).grid(row=3, column=0, sticky="w", padx=12)
        self.tmpl_text = tk.Text(frm, font=FB, bg=PANEL, fg=TEXT,
                                 relief="flat", wrap="word",
                                 highlightbackground=BORDER, highlightthickness=1,
                                 insertbackground=TEXT)
        self.tmpl_text.grid(row=3, column=0, sticky="nsew", padx=12, pady=(2, 4))
        self.tmpl_text.bind("<KeyRelease>", lambda e: self._on_tmpl_edit())

        hint_frm = tk.Frame(frm, bg=PANEL)
        hint_frm.grid(row=4, column=0, sticky="ew", padx=12, pady=(0, 4))
        tk.Label(hint_frm, text="변수:", font=FS, bg=PANEL,
                 fg=SUBTEXT).pack(side="left")
        for var, desc in list_variables():
            tk.Button(hint_frm, text=var, font=FS, bg="#EEF2FF",
                      fg=INDIGO, relief="flat", cursor="hand2", padx=3,
                      command=lambda v=var: self._insert_var(v)).pack(side="left", padx=1)

        prev_frm = tk.Frame(frm, bg="#EEF2FF")
        prev_frm.grid(row=5, column=0, sticky="ew", padx=12, pady=(0, 8))
        tk.Label(prev_frm, text="미리보기 (첫 번째 학생)", font=FS,
                 bg="#EEF2FF", fg=INDIGO).pack(anchor="w", padx=6, pady=(4, 0))
        self.preview_lbl = tk.Label(prev_frm, text="", font=FS,
                                    bg="#EEF2FF", fg=TEXT,
                                    justify="left", anchor="w", wraplength=480)
        self.preview_lbl.pack(fill="x", padx=6, pady=(0, 6))

        send_frm = tk.Frame(frm, bg=PANEL)
        send_frm.grid(row=6, column=0, sticky="ew", padx=12, pady=(0, 12))
        self.send_btn = tk.Button(send_frm, text="카카오톡 창 활성화 후 전송",
                                  font=FT, bg=ACCENT, fg=DARK,
                                  relief="flat", cursor="hand2", pady=8,
                                  command=self._send)
        self.send_btn.pack(fill="x")

        self._refresh_template_cb()

    # ══════════════════════════════════════════════════════════════════
    # TAB 3 — 설정
    # ══════════════════════════════════════════════════════════════════
    def _build_settings_tab(self):
        tab = tk.Frame(self.nb, bg=BG)
        self.nb.add(tab, text="  설정  ")
        tab.columnconfigure(1, weight=1)

        fields = [
            ("Firebase URL",    "firebase_url"),
            ("Firebase Path",   "firebase_path"),
            ("카톡 채팅방 접두사", "room_prefix"),
            ("전송 딜레이(초)",   "wait_time"),
        ]
        self._settings_vars = {}
        for i, (label, key) in enumerate(fields):
            tk.Label(tab, text=label, font=FB, bg=BG, fg=TEXT,
                     anchor="w").grid(row=i, column=0, sticky="w", padx=24, pady=10)
            v = tk.StringVar(value=str(self.cfg.get(key, "")))
            self._settings_vars[key] = v
            tk.Entry(tab, textvariable=v, font=FB, width=40,
                     relief="flat", bg=PANEL,
                     highlightbackground=BORDER,
                     highlightthickness=1).grid(row=i, column=1,
                                                padx=8, pady=10, sticky="ew")

        tk.Button(tab, text="저장 & 재연결", font=FT, bg=ACCENT, fg=DARK,
                  relief="flat", cursor="hand2", pady=6,
                  command=self._save_settings).grid(
                      row=len(fields), column=0, columnspan=2,
                      padx=24, pady=16, sticky="ew")

    def _save_settings(self):
        for key, v in self._settings_vars.items():
            val = v.get().strip()
            if key == "wait_time":
                try:
                    self.cfg[key] = float(val)
                except ValueError:
                    self.cfg[key] = 0.5
            else:
                self.cfg[key] = val
        save_settings(self.cfg)
        self._try_load_firebase()
        self._set_status("설정 저장 완료 — Firebase 재연결 중...", GREEN)

    # ══════════════════════════════════════════════════════════════════
    # Firebase 공통
    # ══════════════════════════════════════════════════════════════════
    def _try_load_firebase(self):
        url  = self.cfg.get("firebase_url", "")
        path = self.cfg.get("firebase_path", "")
        if not url or not path:
            self._set_status("Firebase 설정 없음 — 설정 탭에서 URL/Path 입력", RED)
            return
        self._set_status("Firebase 로드 중...", GRAY)
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
        self._on_roster_sheet_change()
        self._on_sheet_change()

    # ── 발송 탭 Firebase 이벤트 ──────────────────────────────────────
    def _on_sheet_change(self):
        sheet   = self.cur_sheet.get()
        classes = sorted(
            self.fb_config.get("sheets", {}).get(sheet, {}).get("classes", {}).keys())
        self.cls_cb["values"] = classes
        if classes:
            self.cur_cls.set(classes[0])
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
        sheet = self.cur_sheet.get()
        cls   = self.cur_cls.get()
        if not cls:
            return
        self.fb_scores = {}

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

    # ── 학생 목록 렌더 (발송 탭) ─────────────────────────────────────
    def _render_students(self, students):
        sheet = self.cur_sheet.get()
        cls   = self.cur_cls.get()
        cls_vars = (self.send_selections
                        .setdefault(sheet, {})
                        .setdefault(cls, {}))

        for w in self.student_frame.winfo_children():
            w.destroy()
        self.student_vars.clear()

        for s in sorted(students, key=lambda x: x.get("name", "")):
            name = s.get("name", "")
            if name not in cls_vars:
                cls_vars[name] = tk.BooleanVar(value=False)
            var = cls_vars[name]
            self.student_vars[name] = var
            cb = tk.Checkbutton(self.student_frame, text=name,
                                variable=var, font=FB,
                                bg=PANEL, fg=TEXT, selectcolor=PANEL,
                                anchor="w", command=self._update_sel_count)
            cb.pack(fill="x", padx=8, pady=1)

        self._update_sel_count()
        self._update_preview()

    def _select_all(self, val: bool):
        for v in self.student_vars.values():
            v.set(val)
        self._update_sel_count()
        self._update_preview()

    def _clear_all_selections(self):
        for cls_dict in self.send_selections.values():
            for name_dict in cls_dict.values():
                for v in name_dict.values():
                    v.set(False)
        self._update_sel_count()
        self._update_preview()

    def _update_sel_count(self):
        total = sum(
            v.get()
            for cls_dict in self.send_selections.values()
            for name_dict in cls_dict.values()
            for v in name_dict.values()
        )
        classes = sum(
            1 for sh, cls_dict in self.send_selections.items()
            for cls, name_dict in cls_dict.items()
            if any(v.get() for v in name_dict.values())
        )
        if classes > 1:
            self.sel_label.config(text=f"{total}명 선택 ({classes}개 반)")
        else:
            self.sel_label.config(text=f"{total}명 선택")

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
        t     = self.templates[idx]
        ttype = t.get("type", "common")
        self.tmpl_text.delete("1.0", "end")
        self.tmpl_text.insert("1.0", t.get("body", ""))
        self.tmpl_type_lbl.config(
            text="[성적 참조]" if ttype == "score" else "[일반]",
            fg=INDIGO if ttype == "score" else SUBTEXT)
        if ttype == "score":
            self.score_frm.grid()
        else:
            self.score_frm.grid_remove()
        self._update_preview()

    def _on_tmpl_edit(self):
        if 0 <= self.tmpl_idx < len(self.templates):
            self.templates[self.tmpl_idx]["body"] = self.tmpl_text.get("1.0", "end-1c")
            save_templates(self.templates)
        self._update_preview()

    def _add_template(self):
        name = simpledialog.askstring("템플릿 추가", "템플릿 이름:", parent=self.root)
        if not name:
            return
        ttype = messagebox.askquestion(
            "유형 선택", "성적 참조 템플릿입니까?\n(예=성적참조 / 아니오=일반)",
            parent=self.root)
        self.templates.append({
            "name": name,
            "type": "score" if ttype == "yes" else "common",
            "body": "",
        })
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
                test_key  = self._get_selected_test_key()
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

        body   = self.tmpl_text.get("1.0", "end-1c")
        prefix = self.cfg.get("room_prefix", "오직 ")
        is_score = (0 <= self.tmpl_idx < len(self.templates) and
                    self.templates[self.tmpl_idx].get("type") == "score")

        # 전체 반에서 선택된 학생 수집
        selected_by_cls = {}   # (sheet, cls) → [name, ...]
        for sh, cls_dict in self.send_selections.items():
            for cls, name_dict in cls_dict.items():
                names = [n for n, v in name_dict.items() if v.get()]
                if names:
                    selected_by_cls[(sh, cls)] = names

        if not selected_by_cls:
            messagebox.showinfo("알림", "전송 대상 학생을 선택하세요.")
            return

        # 성적 참조 템플릿은 현재 반만 지원
        if is_score:
            cur_sh  = self.cur_sheet.get()
            cur_cls = self.cur_cls.get()
            multi   = [(sh, cls) for sh, cls in selected_by_cls if (sh, cls) != (cur_sh, cur_cls)]
            if multi:
                messagebox.showinfo("안내",
                    "성적 참조 템플릿은 현재 선택된 반만 발송됩니다.\n"
                    "다른 반 선택 학생은 제외됩니다.")
            selected_by_cls = {(cur_sh, cur_cls): selected_by_cls.get((cur_sh, cur_cls), [])}
            if not selected_by_cls.get((cur_sh, cur_cls)):
                messagebox.showinfo("알림", "현재 반에서 선택된 학생이 없습니다.")
                return

        test_key  = self._get_selected_test_key() if is_score else None
        test_data = self.fb_scores.get(test_key, {}) if test_key else {}

        msgs = []
        for (sh, cls), names in selected_by_cls.items():
            if is_score:
                score_map = test_data.get("students", {})
                no_score  = [n for n in names if n not in score_map]
                names     = [n for n in names if n in score_map]
                if no_score:
                    messagebox.showinfo("안내",
                        f"점수 없는 학생 {len(no_score)}명 제외:\n" + ", ".join(no_score))
            for name in names:
                ctx = (build_score_ctx(name, cls, test_data) if is_score
                       else build_common_ctx(name, cls))
                msgs.append({"room": f"{prefix}{name}", "msg": render(body, ctx)})

        if not msgs:
            messagebox.showinfo("알림", "전송 가능한 학생이 없습니다.")
            return

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
