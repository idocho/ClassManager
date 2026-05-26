"""
kakao_send.py — KakaoTalk 자동 전송 (pyautogui + pyperclip)
Extracted from DailyReportWizard2 · Crafted by IDO(idocho@kakao.com)
"""
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


def send_messages(msgs, wait_time=0.5, status_cb=None, done_cb=None):
    """
    카카오톡 채팅방 순차 전송.

    msgs: [{"room": "오직 홍길동", "msg": "전송할 메시지"}, ...]
    wait_time: 각 단계 사이 딜레이(초)
    status_cb(text): 진행 상태 콜백
    done_cb(total): 완료 콜백
    """
    def _run():
        total = len(msgs)
        time.sleep(3)
        for i, m in enumerate(msgs):
            if status_cb:
                status_cb(f"전송 중... ({i+1}/{total})  {m['room']}")
            try:
                pyperclip.copy(m['room'])
                pyautogui.hotkey(_MOD, 'f'); time.sleep(0.2)
                pyautogui.press('esc');      time.sleep(0.2)
                pyautogui.hotkey(_MOD, 'f'); time.sleep(wait_time)
                pyautogui.hotkey(_MOD, 'v'); time.sleep(wait_time)
                pyautogui.press('enter');    time.sleep(wait_time)
                pyperclip.copy(m['msg'])
                pyautogui.hotkey(_MOD, 'v'); time.sleep(0.2)
                pyautogui.press('enter');    time.sleep(0.3)
                pyautogui.press('esc')
            except Exception as e:
                print(f"오류 [{m['room']}]: {e}")
            time.sleep(0.8)
        if done_cb:
            done_cb(total)

    threading.Thread(target=_run, daemon=True).start()
