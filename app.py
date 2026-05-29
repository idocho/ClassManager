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
    return {"dbUrl": "", "dbPath": "", "wait_time": 0.5, "room_prefix": "오직 "}


def save_settings(config: dict):
    with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)


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

        self.config    = load_settings()
        self.templates = load_templates()

        # Firebase 로드 데이터 (v2.0 스키마)
        self.classData  = {}   # classes/{classId} → {group, courses/...}
        self.studentsData = {} # students/{nameKey} → {name, class}  # nameKey = 출결번호
        self.scoreData  = {}   # scores/weekly/{classId}/{subject}/{testKey}

        # 명단 탭 상태
        self.activeGroup     = tk.StringVar(value="M")
        self._roster_classId = ""
        self._roster_sel_stu = []   # [(nameKey, displayName), ...]

        # 발송 탭 상태
        self.cur_group       = tk.StringVar(value="M")
        self.cur_classId     = tk.StringVar(value="")
        self.student_vars    = {}
        self.send_selections = {}   # {classId: {nameKey: BooleanVar}}
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
        self._build_unassigned_tab()
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

        # 그룹(시트) 선택
        sh_frm = tk.Frame(frm, bg=PANEL)
        sh_frm.pack(fill="x", padx=10, pady=(10, 4))
        tk.Label(sh_frm, text="그룹", font=FS, bg=PANEL, fg=SUBTEXT).pack(side="left")
        for s in ("M", "T"):
            tk.Radiobutton(sh_frm, text=s, variable=self.activeGroup, value=s,
                           bg=PANEL, fg=TEXT, font=FB, selectcolor=PANEL,
                           command=self._on_roster_group_change).pack(side="left", padx=6)

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
            ("학생 삭제",      self._roster_del_student,   RED),
        ]:
            tk.Button(btn_frm, text=text, font=FS, bg=PANEL, fg=fg,
                      relief="flat", cursor="hand2",
                      command=cmd).pack(side="left", padx=2)

        self.roster_count_lbl = tk.Label(frm, text="", font=FS, bg=PANEL, fg=SUBTEXT)
        self.roster_count_lbl.grid(row=3, column=0, sticky="w", padx=12, pady=(0, 8))

    # ── 명단 탭 이벤트 ────────────────────────────────────────────────
    def _on_roster_group_change(self):
        """activeGroup(M/T) 변경 시 해당 그룹의 반 목록을 갱신."""
        group = self.activeGroup.get()
        classes = sorted(
            classId for classId, data in self.classData.items()
            if data.get("group") == group
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
        classId = self.cls_listbox.get(sel[0])
        self._roster_classId = classId
        group = self.activeGroup.get()

        # students/{nameKey} 중 class == classId 필터링
        class_students = {
            k: v for k, v in self.studentsData.items()
            if v.get("class") == classId
        }
        self.roster_cls_lbl.config(text=f"{classId}  ({group}그룹)")
        self.student_listbox.delete(0, "end")
        # Listbox에 항상 "이름 (출결번호)" 형식으로 표시
        for nameKey in sorted(class_students.keys()):
            display = class_students[nameKey].get("name", nameKey)
            self.student_listbox.insert("end", f"{display} ({nameKey})")
        self.roster_count_lbl.config(text=f"총 {len(class_students)}명")
        self._roster_sel_stu = []

    def _get_roster_cls(self):
        if not self._roster_classId:
            messagebox.showinfo("알림", "반을 먼저 선택하세요.", parent=self.root)
            return None
        return self._roster_classId

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
        """선택된 학생의 표시 문자열 목록 반환."""
        sel = self.student_listbox.curselection()
        if sel:
            self._roster_sel_stu = [self.student_listbox.get(i) for i in sel]
        return self._roster_sel_stu

    def _display_to_namekey(self, display: str) -> str:
        """Listbox 표시 문자열 → nameKey 변환. 항상 '이름 (출결번호)' 형식."""
        if "(" in display and display.endswith(")"):
            return display.rsplit("(", 1)[1].rstrip(")")
        return display  # fallback

    # ── 반 CRUD ───────────────────────────────────────────────────────
    def _roster_add_class(self):
        classId = simpledialog.askstring("반 추가", "새 반 ID (예: 3MAM):", parent=self.root)
        if not classId:
            return
        classId = classId.strip()
        group   = self.activeGroup.get()

        if classId in self.classData:
            messagebox.showinfo("알림", f"'{classId}'은 이미 존재하는 반입니다.",
                                parent=self.root)
            return

        new_class_data = {"group": group}
        self.classData[classId] = new_class_data

        def _write():
            try:
                firebase_put(self.config, f"classes/{classId}", new_class_data)
                self.root.after(0, lambda: (
                    self._on_roster_group_change(),
                    self._set_status(f"반 '{classId}' 추가 완료", GREEN)))
            except Exception as e:
                self.root.after(0, lambda e=e: self._set_status(f"오류: {e}", RED))
        threading.Thread(target=_write, daemon=True).start()

    def _roster_del_class(self):
        classId = self._get_roster_cls()
        if not classId:
            return
        if not messagebox.askyesno(
                "반 삭제",
                f"'{classId}' 반을 삭제합니까?\n소속 학생은 무소속으로 전환됩니다.",
                parent=self.root):
            return
        self.classData.pop(classId, None)
        # 로컬 학생 데이터 class → None
        affected = [k for k, v in self.studentsData.items()
                    if v.get("class") == classId]
        for k in affected:
            self.studentsData[k]["class"] = None

        def _write():
            try:
                # 1. classes/{classId} 삭제
                firebase_delete(self.config, f"classes/{classId}")
                # 2. 소속 학생 class → null
                for nameKey in affected:
                    firebase_patch(self.config, f"students/{nameKey}", {"class": None})
                self.root.after(0, lambda: (
                    self._on_roster_group_change(),
                    self._set_status(f"반 '{classId}' 삭제 완료", GREEN)))
            except Exception as e:
                self.root.after(0, lambda e=e: self._set_status(f"오류: {e}", RED))
        threading.Thread(target=_write, daemon=True).start()

    def _roster_rename_class(self):
        classId = self._get_roster_cls()
        if not classId:
            return
        new_name = simpledialog.askstring("반 이름 변경", f"'{classId}' → 새 ID:",
                                          parent=self.root)
        if not new_name or new_name.strip() == classId:
            return
        new_name = new_name.strip()
        cls_data = self.classData.get(classId, {})
        self.classData[new_name] = cls_data
        self.classData.pop(classId, None)
        # 소속 학생 class 필드 업데이트 (로컬)
        affected = [k for k, v in self.studentsData.items()
                    if v.get("class") == classId]
        for k in affected:
            self.studentsData[k]["class"] = new_name

        def _write():
            try:
                firebase_put(self.config, f"classes/{new_name}", cls_data)
                firebase_delete(self.config, f"classes/{classId}")
                for nameKey in affected:
                    firebase_patch(self.config, f"students/{nameKey}", {"class": new_name})
                self.root.after(0, lambda: (
                    self._on_roster_group_change(),
                    self._set_status(f"'{classId}' → '{new_name}' 변경 완료", GREEN)))
            except Exception as e:
                self.root.after(0, lambda e=e: self._set_status(f"오류: {e}", RED))
        threading.Thread(target=_write, daemon=True).start()

    # ── 학생 CRUD ─────────────────────────────────────────────────────
    def _ask_student_form(self, classId):
        """출결번호 + 이름을 한 폼에서 입력받아 (hak, name) 반환. 취소 시 None."""
        dlg = tk.Toplevel(self.root)
        dlg.title("학생 추가")
        dlg.configure(bg=PANEL)
        dlg.transient(self.root)
        dlg.resizable(False, False)
        result = {"ok": False}

        frm = tk.Frame(dlg, bg=PANEL)
        frm.pack(padx=18, pady=16)
        frm.columnconfigure(0, weight=1)

        tk.Label(frm, text=f"반: {classId}", font=FS, bg=PANEL,
                 fg=SUBTEXT, anchor="w").grid(row=0, column=0, sticky="w", pady=(0, 8))
        tk.Label(frm, text="출결번호 (필수)", font=FS, bg=PANEL,
                 fg=TEXT, anchor="w").grid(row=1, column=0, sticky="w")
        hak_var = tk.StringVar()
        e1 = tk.Entry(frm, textvariable=hak_var, font=FB, width=26)
        e1.grid(row=2, column=0, sticky="ew", pady=(2, 10))
        tk.Label(frm, text="이름 (필수)", font=FS, bg=PANEL,
                 fg=TEXT, anchor="w").grid(row=3, column=0, sticky="w")
        name_var = tk.StringVar()
        e2 = tk.Entry(frm, textvariable=name_var, font=FB, width=26)
        e2.grid(row=4, column=0, sticky="ew", pady=(2, 14))

        btns = tk.Frame(frm, bg=PANEL)
        btns.grid(row=5, column=0, sticky="e")

        def _ok(*_):
            result["ok"] = True
            dlg.destroy()

        def _cancel(*_):
            dlg.destroy()

        tk.Button(btns, text="취소", font=FB, command=_cancel).pack(side="right", padx=(6, 0))
        tk.Button(btns, text="추가", font=FB, bg=INDIGO, fg="white",
                  command=_ok).pack(side="right")

        # Enter: 출결번호→이름 이동, 이름에서 제출 / Esc: 취소
        e1.bind("<Return>", lambda e: e2.focus_set())
        e2.bind("<Return>", _ok)
        dlg.bind("<Escape>", _cancel)

        e1.focus_set()
        dlg.grab_set()
        self.root.wait_window(dlg)

        if not result["ok"]:
            return None
        return hak_var.get().strip(), name_var.get().strip()

    def _roster_add_student(self):
        classId = self._get_roster_cls()
        if not classId:
            return

        form = self._ask_student_form(classId)
        if not form:
            return
        hak, name = form
        if not hak or not name:
            messagebox.showwarning("입력 오류",
                "출결번호와 이름을 모두 입력하세요.", parent=self.root)
            return
        if hak in self.studentsData:
            messagebox.showwarning("중복",
                f"출결번호 '{hak}'은 이미 등록된 학생입니다.", parent=self.root)
            return

        nameKey = hak  # 출결번호 = nameKey
        student_doc = {"name": name, "class": classId}
        self.studentsData[nameKey] = student_doc

        def _write():
            try:
                firebase_put(self.config, f"students/{nameKey}", student_doc)
                self.root.after(0, lambda: (
                    self._on_roster_cls_select(),
                    self._set_status(f"'{name}' 추가 완료", GREEN)))
            except Exception as e:
                self.root.after(0, lambda e=e: self._set_status(f"오류: {e}", RED))
        threading.Thread(target=_write, daemon=True).start()

    def _roster_del_student(self):
        classId = self._get_roster_cls()
        if not classId:
            return
        selected_displays = self._get_selected_students()
        if not selected_displays:
            messagebox.showinfo("알림", "학생을 선택하세요.", parent=self.root)
            return
        selected_namekeys = [self._display_to_namekey(d) for d in selected_displays]
        selected_names    = [self.studentsData.get(k, {}).get("name", k)
                             for k in selected_namekeys]

        if not messagebox.askyesno(
                "학생 삭제",
                f"{len(selected_namekeys)}명을 완전 삭제합니까?\n" + ", ".join(selected_names),
                parent=self.root):
            return

        for k in selected_namekeys:
            self.studentsData.pop(k, None)

        def _write():
            try:
                for nameKey in selected_namekeys:
                    firebase_delete(self.config, f"students/{nameKey}")
                self.root.after(0, lambda: (
                    self._on_roster_cls_select(),
                    self._set_status(f"{len(selected_namekeys)}명 삭제 완료", GREEN)))
            except Exception as e:
                self.root.after(0, lambda e=e: self._set_status(f"오류: {e}", RED))
        threading.Thread(target=_write, daemon=True).start()

    def _roster_move_student(self):
        classId = self._get_roster_cls()
        if not classId:
            return
        selected_displays = self._get_selected_students()
        if not selected_displays:
            messagebox.showinfo("알림", "학생을 선택하세요.", parent=self.root)
            return
        selected_namekeys = [self._display_to_namekey(d) for d in selected_displays]

        dlg = tk.Toplevel(self.root)
        dlg.title("반 이관")
        dlg.configure(bg=BG)
        dlg.geometry("360x210")
        dlg.grab_set()

        tk.Label(dlg, text=f"{len(selected_namekeys)}명 이관 — 대상 반 선택",
                 font=FB, bg=BG, fg=TEXT).pack(pady=(16, 8))

        row = tk.Frame(dlg, bg=BG)
        row.pack(pady=4)
        dst_group_var = tk.StringVar(value=self.activeGroup.get())
        for s in ("M", "T"):
            tk.Radiobutton(row, text=s, variable=dst_group_var, value=s,
                           bg=BG, fg=TEXT, font=FB,
                           selectcolor=BG).pack(side="left", padx=8)

        targetClassId_var = tk.StringVar()
        dst_cb = ttk.Combobox(dlg, textvariable=targetClassId_var,
                              state="readonly", width=22, font=FB)
        dst_cb.pack(pady=8)

        def _update_cls_list(*_):
            grp = dst_group_var.get()
            classes = sorted(
                cid for cid, d in self.classData.items()
                if d.get("group") == grp and cid != classId
            )
            dst_cb["values"] = classes
            targetClassId_var.set("")
        dst_group_var.trace_add("write", _update_cls_list)
        _update_cls_list()

        def _confirm():
            targetClassId = targetClassId_var.get()
            if not targetClassId:
                messagebox.showinfo("알림", "이관할 반을 선택하세요.", parent=dlg)
                return
            dlg.destroy()
            self._do_move_students(selected_namekeys, classId, targetClassId)

        tk.Button(dlg, text="이관", font=FT, bg=ACCENT, fg=DARK,
                  relief="flat", cursor="hand2", pady=6,
                  command=_confirm).pack(fill="x", padx=24, pady=8)

    def _do_move_students(self, nameKeys: list, sourceClassId: str, targetClassId: str):
        self._set_status(f"{len(nameKeys)}명 이관 중...", GRAY)

        def _worker():
            try:
                for nameKey in nameKeys:
                    firebase_patch(self.config, f"students/{nameKey}", {"class": targetClassId})
                    if nameKey in self.studentsData:
                        self.studentsData[nameKey]["class"] = targetClassId

                self.root.after(0, lambda: (
                    self._on_roster_group_change(),
                    self._set_status(
                        f"{len(nameKeys)}명 이관 완료 → {targetClassId}", GREEN)))
            except Exception as e:
                self.root.after(0, lambda e=e: self._set_status(f"이관 오류: {e}", RED))

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
        rows = []
        for nameKey, data in sorted(self.studentsData.items()):
            rows.append((
                nameKey,
                data.get("name", nameKey),
                data.get("class", ""),
            ))
        rows.sort(key=lambda r: (r[2] or "", r[1]))
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(["출결번호", "name", "class"])
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
            new_students = {}
            with open(path, newline="", encoding="utf-8-sig") as f:
                for row in csv.DictReader(f):
                    nameKey = row.get("출결번호", "").strip()
                    if not nameKey:
                        continue
                    name    = row.get("name", "").strip() or nameKey
                    classId = row.get("class", "").strip() or None
                    new_students[nameKey] = {"name": name, "class": classId}
        except Exception as e:
            messagebox.showerror("오류", f"CSV 파싱 실패: {e}", parent=self.root)
            return

        total = len(new_students)
        if not messagebox.askyesno(
                "Import 확인",
                f"기존 학생 명단 전체를 덮어씁니다.\n총 {total}명\n\n진행합니까?",
                parent=self.root):
            return

        def _upload():
            try:
                # 새 경로/누락 반 자동 생성 (기존 반 group 은 보존)
                existing = firebase_get(self.config, "classes")
                existing = existing if isinstance(existing, dict) else {}
                needed   = {v["class"] for v in new_students.values() if v.get("class")}
                missing  = {c: {"group": self._infer_group(c)}
                            for c in needed if c not in existing}
                if missing:
                    firebase_patch(self.config, "classes", missing)

                firebase_put(self.config, "students", new_students)

                cls2 = firebase_get(self.config, "classes")
                self.classData    = cls2 if isinstance(cls2, dict) else {}
                data2 = firebase_get(self.config, "students")
                self.studentsData = data2 if isinstance(data2, dict) else {}
                self.root.after(0, lambda: (
                    self._on_roster_group_change(),
                    self._on_group_change(),
                    self._refresh_unassigned(),
                    self._set_status(
                        f"Import 완료 — {total}명, 반 {len(missing)}개 자동 생성", GREEN)))
            except Exception as e:
                self.root.after(0, lambda e=e: self._set_status(f"Import 오류: {e}", RED))

        threading.Thread(target=_upload, daemon=True).start()

    @staticmethod
    def _infer_group(classId):
        """반 이름으로 M/T 그룹 추론. 개별화→T, 코드 끝글자 M/T, 그 외 M."""
        if "개별화" in classId:
            return "T"
        last = classId[-1] if classId else ""
        return last if last in ("M", "T") else "M"

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
        tk.Label(sh_frm, text="그룹", font=FS, bg=PANEL, fg=SUBTEXT).pack(side="left")
        for s in ("M", "T"):
            tk.Radiobutton(sh_frm, text=s, variable=self.cur_group, value=s,
                           bg=PANEL, fg=TEXT, font=FB, selectcolor=PANEL,
                           command=self._on_group_change).pack(side="left", padx=6)

        cls_frm = tk.Frame(frm, bg=PANEL)
        cls_frm.pack(fill="x", padx=10, pady=(0, 6))
        tk.Label(cls_frm, text="반", font=FS, bg=PANEL, fg=SUBTEXT).pack(side="left")
        self.cls_cb = ttk.Combobox(cls_frm, textvariable=self.cur_classId,
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
    # TAB 3 — 무소속 학생
    # ══════════════════════════════════════════════════════════════════
    def _build_unassigned_tab(self):
        tab = tk.Frame(self.nb, bg=BG)
        self.nb.add(tab, text="  무소속 학생  ")
        tab.columnconfigure(0, weight=1)
        tab.rowconfigure(1, weight=1)
        self._unassigned_tab = tab

        hdr = tk.Frame(tab, bg=BG)
        hdr.grid(row=0, column=0, sticky="ew", padx=8, pady=(8, 4))
        tk.Label(hdr, text="반이 배정되지 않은 학생", font=FT,
                 bg=BG, fg=TEXT).pack(side="left")
        tk.Button(hdr, text="↺ 새로고침", font=FS, bg=PANEL, fg=INDIGO,
                  relief="flat", cursor="hand2",
                  command=self._refresh_unassigned).pack(side="right")

        # 스크롤 가능한 목록 영역
        sc_frm = tk.Frame(tab, bg=BG)
        sc_frm.grid(row=1, column=0, sticky="nsew", padx=8, pady=(0, 8))
        sc_frm.rowconfigure(0, weight=1)
        sc_frm.columnconfigure(0, weight=1)

        self._unassigned_canvas = tk.Canvas(sc_frm, bg=PANEL, highlightthickness=0)
        sb = tk.Scrollbar(sc_frm, orient="vertical",
                          command=self._unassigned_canvas.yview)
        self._unassigned_canvas.configure(yscrollcommand=sb.set)
        self._unassigned_canvas.grid(row=0, column=0, sticky="nsew")
        sb.grid(row=0, column=1, sticky="ns")

        self._unassigned_frame = tk.Frame(self._unassigned_canvas, bg=PANEL)
        self._unassigned_canvas.create_window((0, 0), window=self._unassigned_frame,
                                              anchor="nw", tags="inner")
        self._unassigned_frame.bind("<Configure>",
            lambda e: self._unassigned_canvas.configure(
                scrollregion=self._unassigned_canvas.bbox("all")))

    def _refresh_unassigned(self):
        """무소속(class=None 또는 누락) 학생 목록을 재렌더링."""
        for w in self._unassigned_frame.winfo_children():
            w.destroy()

        unassigned = {
            k: v for k, v in self.studentsData.items()
            if not v.get("class")
        }

        if not unassigned:
            tk.Label(self._unassigned_frame, text="무소속 학생이 없습니다.",
                     font=FB, bg=PANEL, fg=SUBTEXT).pack(padx=16, pady=16)
            return

        # 컬럼 헤더
        hdr = tk.Frame(self._unassigned_frame, bg=BORDER)
        hdr.pack(fill="x", padx=4, pady=(4, 0))
        for col, w in [("이름", 12), ("출결번호", 10), ("반 배정", 8), ("삭제", 5)]:
            tk.Label(hdr, text=col, font=FS, bg=BORDER, fg=TEXT,
                     width=w, anchor="w").pack(side="left", padx=4, pady=2)

        for nameKey, data in sorted(unassigned.items(),
                                    key=lambda x: x[1].get("name", x[0])):
            row = tk.Frame(self._unassigned_frame, bg=PANEL)
            row.pack(fill="x", padx=4, pady=1)
            tk.Label(row, text=data.get("name", nameKey), font=FB, bg=PANEL,
                     fg=TEXT, width=12, anchor="w").pack(side="left", padx=4)
            tk.Label(row, text=nameKey, font=FB, bg=PANEL,
                     fg=SUBTEXT, width=10, anchor="w").pack(side="left")
            tk.Button(row, text="반 배정", font=FS, bg=INDIGO, fg="white",
                      relief="flat", cursor="hand2", padx=4,
                      command=lambda nk=nameKey: self._assign_class(nk)
                      ).pack(side="left", padx=4)
            tk.Button(row, text="삭제", font=FS, bg=PANEL, fg=RED,
                      relief="flat", cursor="hand2",
                      command=lambda nk=nameKey, nm=data.get("name", nameKey):
                          self._delete_unassigned(nk, nm)
                      ).pack(side="left", padx=2)

    def _assign_class(self, nameKey: str):
        """무소속 학생에게 반을 배정."""
        all_classes = sorted(self.classData.keys())
        if not all_classes:
            messagebox.showinfo("알림", "등록된 반이 없습니다.", parent=self.root)
            return

        dlg = tk.Toplevel(self.root)
        dlg.title("반 배정")
        dlg.configure(bg=BG)
        dlg.geometry("300x160")
        dlg.grab_set()

        name = self.studentsData.get(nameKey, {}).get("name", nameKey)
        tk.Label(dlg, text=f"'{name}' 반 배정", font=FB, bg=BG, fg=TEXT
                 ).pack(pady=(16, 8))

        chosen_var = tk.StringVar()
        cb = ttk.Combobox(dlg, textvariable=chosen_var, values=all_classes,
                          state="readonly", width=20, font=FB)
        cb.pack(pady=8)

        def _confirm():
            targetClassId = chosen_var.get()
            if not targetClassId:
                messagebox.showinfo("알림", "반을 선택하세요.", parent=dlg)
                return
            dlg.destroy()

            def _write():
                try:
                    firebase_patch(self.config, f"students/{nameKey}",
                                   {"class": targetClassId})
                    if nameKey in self.studentsData:
                        self.studentsData[nameKey]["class"] = targetClassId
                    self.root.after(0, lambda: (
                        self._refresh_unassigned(),
                        self._set_status(f"'{name}' → {targetClassId} 배정 완료", GREEN)))
                except Exception as e:
                    self.root.after(0, lambda e=e: self._set_status(f"오류: {e}", RED))
            threading.Thread(target=_write, daemon=True).start()

        tk.Button(dlg, text="배정", font=FT, bg=ACCENT, fg=DARK,
                  relief="flat", cursor="hand2", pady=6,
                  command=_confirm).pack(fill="x", padx=24, pady=8)

    def _delete_unassigned(self, nameKey: str, name: str):
        """무소속 학생 완전 삭제."""
        if not messagebox.askyesno(
                "학생 삭제",
                f"'{name}'을(를) 완전 삭제합니까?",
                parent=self.root):
            return
        self.studentsData.pop(nameKey, None)

        def _write():
            try:
                firebase_delete(self.config, f"students/{nameKey}")
                self.root.after(0, lambda: (
                    self._refresh_unassigned(),
                    self._set_status(f"'{name}' 삭제 완료", GREEN)))
            except Exception as e:
                self.root.after(0, lambda e=e: self._set_status(f"오류: {e}", RED))
        threading.Thread(target=_write, daemon=True).start()

    # ══════════════════════════════════════════════════════════════════
    # TAB 4 — 설정
    # ══════════════════════════════════════════════════════════════════
    def _build_settings_tab(self):
        tab = tk.Frame(self.nb, bg=BG)
        self.nb.add(tab, text="  설정  ")
        tab.columnconfigure(1, weight=1)

        fields = [
            ("Firebase URL",    "dbUrl"),
            ("Firebase Path",   "dbPath"),
            ("카톡 채팅방 접두사", "room_prefix"),
            ("전송 딜레이(초)",   "wait_time"),
        ]
        self._settings_vars = {}
        for i, (label, key) in enumerate(fields):
            tk.Label(tab, text=label, font=FB, bg=BG, fg=TEXT,
                     anchor="w").grid(row=i, column=0, sticky="w", padx=24, pady=10)
            v = tk.StringVar(value=str(self.config.get(key, "")))
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
                    self.config[key] = float(val)
                except ValueError:
                    self.config[key] = 0.5
            else:
                self.config[key] = val
        save_settings(self.config)
        self._try_load_firebase()
        self._set_status("설정 저장 완료 — Firebase 재연결 중...", GREEN)

    # ══════════════════════════════════════════════════════════════════
    # Firebase 공통
    # ══════════════════════════════════════════════════════════════════
    def _try_load_firebase(self):
        url  = self.config.get("dbUrl", "")
        path = self.config.get("dbPath", "")
        if not url or not path:
            self._set_status("Firebase 설정 없음 — 설정 탭에서 URL/Path 입력", RED)
            return
        self._set_status("Firebase 로드 중...", GRAY)
        threading.Thread(target=self._load_fb_data, daemon=True).start()

    def _load_fb_data(self):
        try:
            classes_raw  = firebase_get(self.config, "classes")
            students_raw = firebase_get(self.config, "students")
            self.classData    = classes_raw  if isinstance(classes_raw, dict)  else {}
            self.studentsData = students_raw if isinstance(students_raw, dict) else {}
            self.root.after(0, self._on_fb_loaded)
        except Exception as e:
            self.root.after(0, lambda e=e: self._set_status(f"Firebase 오류: {e}", RED))

    def _on_fb_loaded(self):
        self._set_status("Firebase 연결 완료", GREEN)
        self._on_roster_group_change()
        self._on_group_change()
        self._refresh_unassigned()

    # ── 발송 탭 Firebase 이벤트 ──────────────────────────────────────
    def _on_group_change(self):
        group   = self.cur_group.get()
        classes = sorted(
            classId for classId, data in self.classData.items()
            if data.get("group") == group
        )
        self.cls_cb["values"] = classes
        if classes:
            self.cur_classId.set(classes[0])
            self._on_cls_change()
        else:
            self.cur_classId.set("")
            self._render_students([])

    def _on_cls_change(self):
        classId = self.cur_classId.get()
        if not classId:
            return
        # students/{nameKey} 중 class == classId
        class_students = [
            {"nameKey": k, "name": v.get("name", k)}
            for k, v in self.studentsData.items()
            if v.get("class") == classId
        ]
        self._render_students(class_students)
        self._load_scores()

    def _load_scores(self):
        classId = self.cur_classId.get()
        if not classId:
            return
        self.scoreData = {}

        def _fetch():
            try:
                # scores/weekly/{classId} 전체 로드 (subject → testKey → data)
                data = firebase_get(self.config, f"scores/weekly/{classId}")
                self.scoreData = data if isinstance(data, dict) else {}
            except Exception:
                self.scoreData = {}
            self.root.after(0, self._refresh_score_cb)
        threading.Thread(target=_fetch, daemon=True).start()

    def _refresh_score_cb(self):
        """scoreData(subject→testKey→data) 를 평탄화해 드롭다운 구성."""
        items = []
        for subject, tests in self.scoreData.items():
            if not isinstance(tests, dict):
                continue
            for testKey, v in sorted(tests.items(), reverse=True):
                meta  = v.get("meta", v)   # meta 키 있으면 사용, 없으면 루트
                label = (f"{subject} / {meta.get('date', '')} "
                         f"{meta.get('type', '')} {meta.get('round', '')}").strip()
                items.append((subject, testKey, label))
        self._score_items = items
        self.score_cb["values"] = [lbl for _, _, lbl in items]
        if items:
            self.score_var.set(items[0][2])
        else:
            self.score_var.set("")
        self._update_preview()

    def _get_selected_test_data(self):
        """선택된 시험의 (subject, testKey, data dict) 반환."""
        sel = self.score_var.get()
        for subject, testKey, lbl in getattr(self, "_score_items", []):
            if lbl == sel:
                data = self.scoreData.get(subject, {}).get(testKey, {})
                return subject, testKey, data
        return None, None, {}

    # ── 학생 목록 렌더 (발송 탭) ─────────────────────────────────────
    def _render_students(self, students):
        """students: list of {nameKey, name}"""
        classId  = self.cur_classId.get()
        cls_vars = self.send_selections.setdefault(classId, {})

        for w in self.student_frame.winfo_children():
            w.destroy()
        self.student_vars.clear()

        for s in sorted(students, key=lambda x: x.get("name", "")):
            nameKey = s.get("nameKey", s.get("name", ""))
            name    = s.get("name", nameKey)
            if nameKey not in cls_vars:
                cls_vars[nameKey] = tk.BooleanVar(value=False)
            var = cls_vars[nameKey]
            self.student_vars[nameKey] = var
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
        for name_dict in self.send_selections.values():
            for v in name_dict.values():
                v.set(False)
        self._update_sel_count()
        self._update_preview()

    def _update_sel_count(self):
        total = sum(
            v.get()
            for name_dict in self.send_selections.values()
            for v in name_dict.values()
        )
        classes = sum(
            1 for name_dict in self.send_selections.values()
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
        selected_namekeys = [nk for nk, v in self.student_vars.items() if v.get()]
        if not selected_namekeys:
            self.preview_lbl.config(text="(선택된 학생 없음)")
            return
        nameKey = selected_namekeys[0]
        name    = self.studentsData.get(nameKey, {}).get("name", nameKey)
        classId = self.cur_classId.get()
        body    = self.tmpl_text.get("1.0", "end-1c") if self.tmpl_text.winfo_exists() else ""
        try:
            if (0 <= self.tmpl_idx < len(self.templates) and
                    self.templates[self.tmpl_idx].get("type") == "score"):
                _, _, test_data = self._get_selected_test_data()
                ctx = build_score_ctx(name, classId, test_data)
            else:
                ctx = build_common_ctx(name, classId)
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

        body     = self.tmpl_text.get("1.0", "end-1c")
        prefix   = self.config.get("room_prefix", "오직 ")
        is_score = (0 <= self.tmpl_idx < len(self.templates) and
                    self.templates[self.tmpl_idx].get("type") == "score")

        # 전체 반에서 선택된 학생 수집 {classId: [nameKey, ...]}
        selected_by_cls = {}
        for classId, name_dict in self.send_selections.items():
            nameKeys = [nk for nk, v in name_dict.items() if v.get()]
            if nameKeys:
                selected_by_cls[classId] = nameKeys

        if not selected_by_cls:
            messagebox.showinfo("알림", "전송 대상 학생을 선택하세요.")
            return

        # 성적 참조 템플릿은 현재 반만 지원
        if is_score:
            cur_cls = self.cur_classId.get()
            multi   = [cid for cid in selected_by_cls if cid != cur_cls]
            if multi:
                messagebox.showinfo("안내",
                    "성적 참조 템플릿은 현재 선택된 반만 발송됩니다.\n"
                    "다른 반 선택 학생은 제외됩니다.")
            selected_by_cls = {cur_cls: selected_by_cls.get(cur_cls, [])}
            if not selected_by_cls.get(cur_cls):
                messagebox.showinfo("알림", "현재 반에서 선택된 학생이 없습니다.")
                return

        _, _, test_data = self._get_selected_test_data() if is_score else (None, None, {})

        msgs = []
        for classId, nameKeys in selected_by_cls.items():
            if is_score:
                score_map = test_data.get("students", {})
                no_score  = [nk for nk in nameKeys if nk not in score_map]
                nameKeys  = [nk for nk in nameKeys if nk in score_map]
                if no_score:
                    no_score_names = [
                        self.studentsData.get(nk, {}).get("name", nk) for nk in no_score
                    ]
                    messagebox.showinfo("안내",
                        f"점수 없는 학생 {len(no_score)}명 제외:\n" +
                        ", ".join(no_score_names))
            for nameKey in nameKeys:
                name = self.studentsData.get(nameKey, {}).get("name", nameKey)
                ctx  = (build_score_ctx(name, classId, test_data) if is_score
                        else build_common_ctx(name, classId))
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
        wait = self.config.get("wait_time", 0.5)

        def _status(text):
            self.root.after(0, lambda: self._set_status(text))

        def _done(total):
            def _ui():
                self._set_status(f"✅ 전송 완료 — {total}명", GREEN)
                self.send_btn.config(state="normal")
                messagebox.showinfo("완료", f"{total}명 전송 완료!")
            self.root.after(0, _ui)

        send_messages(msgs, wait_time=wait, status_cb=_status, done_cb=_done)
