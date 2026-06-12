# SmartWait(전송 속도 자동 적응) 단위 테스트 — DRW v8.11 시뮬레이션 검증 항목 재현
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from kakao_send import SmartWait


def test_initial_clamped():
    assert SmartWait(0.5).wait == 0.5
    assert SmartWait(99).wait == SmartWait.MAX
    assert SmartWait(0.01).wait == SmartWait.MIN
    assert SmartWait(None).wait == 0.5
    assert SmartWait("bad").wait == 0.5


def test_fast_system_converges_to_min():
    """빠른 시스템(t_open 0.1s) — 몇 건 안에 하한 수렴."""
    c = SmartWait(0.5)
    for _ in range(6):
        c.adjust(0.1, False)
    assert c.wait == SmartWait.MIN


def test_failure_backs_off_multiplicatively():
    """1차 실패 → ×1.6 즉시 감속."""
    c = SmartWait(0.4)
    c.adjust(1.0, True)
    assert abs(c.wait - 0.64) < 1e-9
    c.adjust(1.0, True)
    assert abs(c.wait - 1.024) < 1e-9
    c.adjust(1.0, True)
    assert c.wait == SmartWait.MAX  # 상한 클램프


def test_recovery_after_failures():
    """실패로 감속된 뒤 빠른 통과가 이어지면 재수렴."""
    c = SmartWait(0.5)
    c.adjust(1.0, True)
    c.adjust(1.0, True)
    assert c.wait > 1.0
    # EMA가 식을 때까지 보통 통과 → 이후 빠른 통과 연속
    # (상한 1.2 → 하한 0.25는 -0.15/2건 가산 감속으로 약 13건 필요)
    for _ in range(6):
        c.adjust(0.3, False)
    for _ in range(16):
        c.adjust(0.1, False)
    assert c.wait == SmartWait.MIN


def test_ema_preemptive_slowdown():
    """지연 추세(EMA>0.8s)면 재시도 없어도 선제 감속."""
    c = SmartWait(0.5)
    for _ in range(4):
        c.adjust(1.0, False)
    assert c.wait > 0.5


def test_streak_resets_on_normal_pass():
    """빠른 통과 1회 + 보통 통과 → 가속 안 됨(연속 2회 필요)."""
    c = SmartWait(0.5)
    c.adjust(0.1, False)
    c.adjust(0.4, False)
    c.adjust(0.1, False)
    assert c.wait == 0.5
