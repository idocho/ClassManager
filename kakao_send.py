"""
kakao_send.py — KakaoTalk 자동 전송 (pyautogui + pyperclip)
Extracted from DailyReportWizard2 · Crafted by IDO(idocho@kakao.com)
"""
import os
import subprocess
import sys
import time
import threading

try:
    import pyautogui
    import pyperclip
    AUTOMATION = True
except ImportError:
    AUTOMATION = False

_MOD = "command" if sys.platform == "darwin" else "ctrl"
_IS_WIN = sys.platform == "win32"
_IS_MAC = sys.platform == "darwin"
_CREATE_NO_WINDOW = 0x08000000  # Windows: 콘솔 창 깜빡임 방지



# ── 이미지 → DIB 캐시 (반복 복사 ~ms — 매번 PowerShell 기동 1~2s 제거) ──
_DIB_CACHE = {}


def _image_to_dib(path: str):
    mtime = os.path.getmtime(path)
    cached = _DIB_CACHE.get(path)
    if cached and cached[0] == mtime:
        return cached[1]
    import tempfile
    bmp_path = os.path.join(tempfile.gettempdir(), f"_cm_clip_{os.getpid()}.bmp")
    safe_in, safe_out = path.replace("'", "''"), bmp_path.replace("'", "''")
    ps = ("Add-Type -AssemblyName System.Drawing;"
          f"$img=[System.Drawing.Image]::FromFile('{safe_in}');"
          "$bmp=New-Object System.Drawing.Bitmap $img;"
          f"$bmp.Save('{safe_out}',[System.Drawing.Imaging.ImageFormat]::Bmp);"
          "$bmp.Dispose();$img.Dispose()")
    subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                   check=True, capture_output=True, creationflags=_CREATE_NO_WINDOW)
    with open(bmp_path, 'rb') as f:
        data = f.read()
    try:
        os.remove(bmp_path)
    except OSError:
        pass
    dib = data[14:]
    _DIB_CACHE.clear()
    _DIB_CACHE[path] = (mtime, dib)
    return dib


def prefetch_image(path: str) -> bool:
    """전송 루프 시작 전 선행 변환 — 첫 건도 무지연. 실패 시 폴백 경로가 처리."""
    if not (_IS_WIN and path and os.path.exists(path)):
        return False
    try:
        _image_to_dib(path)
        return True
    except Exception:
        return False


def _set_clipboard_dib(dib: bytes) -> bool:
    import ctypes
    from ctypes import wintypes
    k32, u32 = ctypes.windll.kernel32, ctypes.windll.user32
    k32.GlobalAlloc.restype = wintypes.HGLOBAL
    k32.GlobalLock.restype = ctypes.c_void_p
    k32.GlobalLock.argtypes = [wintypes.HGLOBAL]
    k32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
    u32.SetClipboardData.restype = wintypes.HANDLE
    u32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
    GMEM_MOVEABLE, CF_DIB = 0x0002, 8
    h = k32.GlobalAlloc(GMEM_MOVEABLE, len(dib))
    if not h:
        return False
    ptr = k32.GlobalLock(h)
    ctypes.memmove(ptr, dib, len(dib))
    k32.GlobalUnlock(h)
    for _ in range(10):
        if u32.OpenClipboard(0):
            break
        time.sleep(0.05)
    else:
        k32.GlobalFree(h)
        return False
    try:
        u32.EmptyClipboard()
        ok = bool(u32.SetClipboardData(CF_DIB, h))
        if not ok:
            k32.GlobalFree(h)
        return ok
    finally:
        u32.CloseClipboard()


def copy_image_to_clipboard(path: str) -> bool:
    """
    이미지 파일을 OS 클립보드에 비트맵으로 복사. 성공 시 True.

    Windows: PowerShell + .NET Clipboard.SetImage (추가 pip 의존성 없음).
             Clipboard.SetImage 는 STA 스레드를 요구하므로 -STA 로 실행.
    macOS:   osascript 로 PNG 데이터를 클립보드에 설정.
    """
    if not path or not os.path.exists(path):
        print(f"이미지 없음: {path}")
        return False
    if _IS_WIN:
        try:
            if _set_clipboard_dib(_image_to_dib(path)):
                return True
        except Exception:
            pass  # PowerShell SetImage 폴백
    try:
        if _IS_WIN:
            safe = path.replace("'", "''")
            ps = (
                "Add-Type -AssemblyName System.Windows.Forms,System.Drawing;"
                f"$img=[System.Drawing.Image]::FromFile('{safe}');"
                "[System.Windows.Forms.Clipboard]::SetImage($img);"
                "$img.Dispose()"
            )
            subprocess.run(
                ["powershell", "-NoProfile", "-STA", "-Command", ps],
                check=True, capture_output=True,
                creationflags=_CREATE_NO_WINDOW,
            )
            return True
        if _IS_MAC:
            safe = path.replace('"', '\\"')
            script = f'set the clipboard to (read (POSIX file "{safe}") as «class PNGf»)'
            subprocess.run(["osascript", "-e", script],
                           check=True, capture_output=True)
            return True
        print(f"이미지 클립보드 복사 미지원 플랫폼: {sys.platform}")
        return False
    except Exception as e:
        print(f"이미지 클립보드 복사 실패 [{path}]: {e}")
        return False


# ── 카카오톡 창 자동 포커스 (DRW kakao_image.py 와 동일 구현) ─────────
# 기존: 전송 시작 후 3초 안에 사용자가 직접 카톡 창을 클릭해야 했음 — 실패 시
# 키 입력이 엉뚱한 창으로 들어가는 간헐 오류의 최다 원인. 자동 포커스로 대체.
_KAKAO_TITLES = ("카카오톡", "KakaoTalk")


def _find_kakao_hwnd():
    """카카오톡 메인 창 HWND. 트레이(invisible)도 탐지 — class EVA_Window_Dblclk 우선."""
    if not _IS_WIN:
        return None
    import ctypes
    from ctypes import wintypes
    user32 = ctypes.windll.user32
    main, fallback = [], []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
    def _enum(hwnd, _):
        t = ctypes.create_unicode_buffer(64)
        user32.GetWindowTextW(hwnd, t, 64)
        if t.value.strip() in _KAKAO_TITLES:
            c = ctypes.create_unicode_buffer(64)
            user32.GetClassNameW(hwnd, c, 64)
            (main if c.value == 'EVA_Window_Dblclk' else fallback).append(hwnd)
        return True

    user32.EnumWindows(_enum, 0)
    return (main or fallback or [None])[0]


def foreground_title() -> str:
    """현재 전면 창 제목. 비 Windows 는 빈 문자열."""
    if not _IS_WIN:
        return ""
    import ctypes
    user32 = ctypes.windll.user32
    buf = ctypes.create_unicode_buffer(256)
    user32.GetWindowTextW(user32.GetForegroundWindow(), buf, 256)
    return buf.value


def room_opened(room: str, tries: int = 15, interval: float = 0.1) -> bool:
    """채팅방 열림 검증 — 전면 창 제목=방 이름 폴링(공백 무시). 미검증 본문 발사 차단.

    공백 무시: 카톡 검색이 공백을 무시해 room_prefix 공백 유무로 제목만 어긋나는
    사례("오직조이도" vs "오직 조이도") 실측 대응. 잔여부 숫자/괄호 허용(인원수)."""
    if not _IS_WIN:
        return True
    import re
    # 포함 비교(공백 무시) — "오직 XXX"는 검색 키워드, 실제 창 제목엔 다른 텍스트 혼재 가능.
    norm = lambda s: re.sub(r'\s+', '', s)
    nr = norm(room)
    if not nr:
        return False
    for _ in range(tries):
        if nr in norm(foreground_title()):
            return True
        time.sleep(interval)
    return False


def copy_text_verified(text: str, timeout: float = 1.5) -> bool:
    """클립보드 복사 후 반영 확인 — 이전 내용 붙여넣기 레이스 차단."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            pyperclip.copy(text)
            time.sleep(0.05)
            if pyperclip.paste() == text:
                return True
        except Exception:
            pass
        time.sleep(0.1)
    return False


def focus_kakao(settle: float = 0.6) -> bool:
    """카카오톡 메인 창 전면화. 성공 시 True. 비 Windows 는 True(기존 수동 방식 유지)."""
    if not _IS_WIN:
        return True
    hwnd = _find_kakao_hwnd()
    if not hwnd:
        return False
    import ctypes
    user32 = ctypes.windll.user32
    SW_RESTORE, VK_MENU, KEYEVENTF_KEYUP = 9, 0x12, 2
    # 빠른 경로: 이미 전면이면 복원/ALT/대기 생략
    if user32.IsWindowVisible(hwnd) and user32.GetForegroundWindow() == hwnd:
        return True
    try:
        if not user32.IsWindowVisible(hwnd) or user32.IsIconic(hwnd):
            user32.ShowWindow(hwnd, SW_RESTORE)   # 트레이/최소화 → 복원
            time.sleep(0.4)
        user32.keybd_event(VK_MENU, 0, 0, 0)      # 포그라운드 권한 우회용 ALT 탭
        user32.keybd_event(VK_MENU, 0, KEYEVENTF_KEYUP, 0)
        user32.SetForegroundWindow(hwnd)
        time.sleep(settle)
        return user32.GetForegroundWindow() == hwnd
    except Exception as e:
        print(f"카카오톡 창 포커스 실패: {e}")
        return False


class SmartWait:
    """전송 속도 자동 적응(AIMD + EMA) — DRW v8.11 스마트 모드 이식.

    신호 = 방 열림 검증 게이트 실측: t_open(Enter→방 열림)과 1차 재시도 여부.
    · 1차 실패(재시도) → wait ×1.6 즉시 감속 (승법 증가)
    · 빠른 통과(t_open≤0.2s) 연속 2회 → wait -0.15s 가속 (가산 감소)
    · 지연 EMA > 0.8s → 선제 +0.1s 감속 (추세 반영)
    범위 [0.25, 1.2]s. 게이트가 바닥을 받치므로 가속해도 오발송 불가 —
    적응은 1차 통과율만 조절. 학습값은 호출측이 config(smart_wait)에 영속.
    """
    MIN, MAX = 0.25, 1.2

    def __init__(self, initial=0.5):
        try:
            initial = float(initial or 0.5)
        except (TypeError, ValueError):
            initial = 0.5
        self.wait = min(self.MAX, max(self.MIN, initial))
        self._ema = None
        self._fast_streak = 0

    def adjust(self, t_open, retried):
        self._ema = t_open if self._ema is None else 0.6 * self._ema + 0.4 * t_open
        if retried:
            self.wait = min(self.MAX, self.wait * 1.6)
            self._fast_streak = 0
        elif self._ema > 0.8:
            self.wait = min(self.MAX, self.wait + 0.1)
            self._fast_streak = 0
        elif t_open <= 0.2:
            self._fast_streak += 1
            if self._fast_streak >= 2:
                self.wait = max(self.MIN, self.wait - 0.15)
                self._fast_streak = 0
        else:
            self._fast_streak = 0


def send_messages(msgs, wait_time=0.5, status_cb=None, done_cb=None, wait_ctrl=None):
    """
    카카오톡 채팅방 순차 전송.

    msgs: [{"room": "오직 홍길동",
            "msg": "전송할 메시지",
            "image": "C:/path/img.png"  (선택),
            "image_first": False        (선택, True면 이미지를 텍스트보다 먼저)}, ...]
    wait_time: 각 단계 사이 딜레이(초) — 고정 프리셋 모드
    status_cb(text): 진행 상태 콜백
    done_cb(total): 완료 콜백
    wait_ctrl: SmartWait 인스턴스(선택) — 주어지면 건마다 wait_ctrl.wait 사용,
               게이트 실측(t_open·재시도)으로 adjust() 호출해 자동 가감속
    """
    # 이미지는 붙여넣기 후 미리보기 팝업 → Enter 확정까지 여유가 필요
    img_wait = max(wait_time, 1.0)

    def _send_text(m):
        if not m.get("msg"):
            return
        if not copy_text_verified(m["msg"]):
            raise RuntimeError(f"본문 클립보드 복사 실패: {m['room']}")
        pyautogui.hotkey(_MOD, "v"); time.sleep(0.15)
        pyautogui.press("enter");    time.sleep(0.2)

    def _send_image(m):
        img = m.get("image")
        if not img:
            return
        if not copy_image_to_clipboard(img):
            return
        if not _IS_WIN:
            pyautogui.hotkey(_MOD, "v"); time.sleep(img_wait)
            pyautogui.press("enter");    time.sleep(img_wait)
            return
        room = m["room"]
        _in_room = lambda: room_opened(room, tries=1, interval=0)
        # 이미지 붙여넣기 → 확인 팝업 등장 대기(간헐 로딩 지연 흡수) → 확인 → 닫힘 검증
        pyautogui.hotkey(_MOD, "v")
        deadline = time.time() + 8.0
        while time.time() < deadline and _in_room():
            time.sleep(0.15)
        if _in_room():
            raise RuntimeError(f"이미지 팝업 미표시(붙여넣기 실패 추정): {room}")
        pyautogui.press("enter")
        deadline = time.time() + 8.0
        while time.time() < deadline and not _in_room():
            time.sleep(0.15)
        if not _in_room():
            pyautogui.press("esc")
            raise RuntimeError(f"이미지 전송 확인 실패(팝업 미종료): {room}")

    def _run():
        total = len(msgs)
        # 이미지 DIB 선행 변환 — 건별 PowerShell 재기동 제거
        for _img in {m.get("image") for m in msgs if m.get("image")}:
            prefetch_image(_img)
        # v2.1: 3초 수동 클릭 대기 → 카톡 창 자동 포커스. 실패 시 키 입력 없이 안전 중단.
        if not focus_kakao():
            if status_cb:
                status_cb("❌ 카카오톡 창을 찾지 못해 중단 — 카톡 실행 확인")
            if done_cb:
                done_cb(0)
            return
        sent = 0
        for i, m in enumerate(msgs):
            if status_cb:
                status_cb(f"전송 중... ({i+1}/{total})  {m['room']}")
            # 매 건 전 메인 창 재포커스 — 전송 중 사용자가 다른 창을 만져도 복구
            if i > 0 and not focus_kakao(0.3):
                if status_cb:
                    status_cb(f"❌ 카톡 창 소실 — {sent}/{total}건에서 중단")
                if done_cb:
                    done_cb(sent)
                return
            try:
                # 스마트 모드: 건마다 학습된 wait 사용 (고정 프리셋이면 wait_time)
                wait = wait_ctrl.wait if wait_ctrl else wait_time
                t_open_box = [None]  # 게이트 실측(Enter→방 열림) — 스마트 적응 신호

                # 채팅방 검색·이동 — 방 열림 검증 게이트 (단일 방 연속 전송·미전송 연쇄 차단)
                def _open(key_gap, search_load, post_enter):
                    """빠른 1차/느린 재시도 프로파일 — 검증 폴링이 통과를 즉시 감지."""
                    if not copy_text_verified(m["room"]):
                        return False
                    pyautogui.hotkey(_MOD, "f"); time.sleep(key_gap)
                    pyautogui.press("esc");      time.sleep(key_gap)
                    pyautogui.hotkey(_MOD, "f"); time.sleep(key_gap)
                    pyautogui.hotkey(_MOD, "v"); time.sleep(search_load)
                    pyautogui.press("enter")
                    _t0 = time.time()
                    time.sleep(post_enter)
                    ok = room_opened(m["room"])
                    t_open_box[0] = time.time() - _t0
                    return ok
                retried = False
                if not _open(max(0.15, wait * 0.5), max(0.3, wait), 0.1):
                    retried = True
                    pyautogui.press("esc"); time.sleep(0.3)
                    focus_kakao(0.4)
                    if not _open(0.3, max(wait, 1.0), 0.5):
                        pyautogui.press("esc")
                        if wait_ctrl:
                            wait_ctrl.adjust(1.5, True)  # 완전 실패 — 최대 지연으로 학습
                        raise RuntimeError(f"채팅방 열기 실패: {m['room']}")
                if wait_ctrl:
                    wait_ctrl.adjust(
                        t_open_box[0] if t_open_box[0] is not None else 1.5, retried)

                # 본문/이미지 전송 (순서는 image_first 로 제어)
                if m.get("image_first"):
                    _send_image(m)
                    _send_text(m)
                else:
                    _send_text(m)
                    _send_image(m)

                # 방 정리: 이미지 보낸 방은 닫지 않음 — 업로드 진행 중 esc 시
                # "전송 중인 파일" 팝업(확인=업로드 취소 위험)에 막힘. 텍스트만이면 esc 탈출.
                if m.get("image"):
                    pass
                elif _IS_WIN:
                    for _ in range(4):
                        pyautogui.press("esc"); time.sleep(0.2)
                        if not room_opened(m["room"], tries=1, interval=0):
                            break
                else:
                    pyautogui.press("esc")
                sent += 1
            except Exception as e:
                print(f"오류 [{m['room']}]: {e}")
            time.sleep(0.3)  # 게이트 검증으로 단축(기존 0.8)
        if done_cb:
            done_cb(sent)

    threading.Thread(target=_run, daemon=True).start()
