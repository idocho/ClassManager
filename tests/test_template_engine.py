"""Tests for template_engine.py"""
import datetime
import pytest
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from template_engine import render, build_common_ctx, build_score_ctx, _percentile, list_variables


# ── render ───────────────────────────────────────────────────────────

def test_render_single_var():
    assert render("{이름} 안녕", {"이름": "김철수"}) == "김철수 안녕"

def test_render_multiple_vars():
    assert render("{이름} {반}", {"이름": "홍길동", "반": "3MGM"}) == "홍길동 3MGM"

def test_render_undefined_var_preserved():
    assert render("{미정의}", {}) == "{미정의}"

def test_render_partial_undefined():
    assert render("{이름} {반}", {"이름": "홍길동"}) == "홍길동 {반}"

def test_render_empty_template():
    assert render("", {}) == ""

def test_render_no_vars():
    assert render("그냥 문자열", {"이름": "홍길동"}) == "그냥 문자열"

def test_render_repeated_var():
    assert render("{이름} {이름}", {"이름": "김"}) == "김 김"


# ── build_common_ctx ─────────────────────────────────────────────────

def test_build_common_ctx_fields():
    ctx = build_common_ctx("김철수", "3MGM")
    assert ctx["이름"] == "김철수"
    assert ctx["반"] == "3MGM"
    today = datetime.date.today()
    assert ctx["날짜"] == f"{today.month}/{today.day}"

def test_build_common_ctx_date_format():
    ctx = build_common_ctx("x", "y")
    # Must be M/D format (no leading zeros)
    parts = ctx["날짜"].split("/")
    assert len(parts) == 2
    assert parts[0] == str(int(parts[0]))  # no leading zero
    assert parts[1] == str(int(parts[1]))


# ── _percentile ──────────────────────────────────────────────────────

def test_percentile_none_score():
    assert _percentile(None, [60, 70, 80]) == "—"

def test_percentile_empty_scores():
    assert _percentile(80, []) == "—"

def test_percentile_lowest():
    scores = [60, 70, 80, 90, 100]
    assert _percentile(60, scores) == 0

def test_percentile_highest():
    scores = [60, 70, 80, 90, 100]
    # beat all 4 other students → 100%
    assert _percentile(100, scores) == 100

def test_percentile_middle():
    scores = [60, 70, 80, 90, 100]
    # 2 below out of 4 others → 50%
    assert _percentile(80, scores) == 50

def test_percentile_single_student():
    # Only student in class: should not be 0th percentile
    result = _percentile(85, [85])
    assert result == 100  # BUG: currently returns 0

def test_percentile_tie():
    # Two students both at 80; one at 60
    # My score 80: 1 below (60), 1 tie (other 80)
    scores = [60, 80, 80]
    result = _percentile(80, scores)
    # Standard percentile rank: (below + 0.5*equal_excluding_self) / total * 100
    # below=1, total=3 → at minimum should be > 0
    assert result > 0

def test_percentile_returns_int():
    assert isinstance(_percentile(80, [60, 80, 100]), int)

def test_percentile_non_numeric_score_safe():
    # If my_score is non-numeric non-None (bad data), should not raise TypeError
    result = _percentile("결석", [60, 70, 80])
    assert result == "—"


# ── build_score_ctx ──────────────────────────────────────────────────

SAMPLE_TEST = {
    "type": "주간Test",
    "round": "1",
    "date": "2026-05-27",
    "max_score": 100,
    "students": {"김철수": 85, "이영희": 90, "박민수": 70},
}

def test_build_score_ctx_basic():
    ctx = build_score_ctx("김철수", "3MGM", SAMPLE_TEST)
    assert ctx["이름"] == "김철수"
    assert ctx["반"] == "3MGM"
    assert ctx["점수"] == 85
    assert ctx["만점"] == 100
    assert ctx["시험명"] == "주간Test 1"

def test_build_score_ctx_stats():
    ctx = build_score_ctx("김철수", "3MGM", SAMPLE_TEST)
    assert ctx["평균"] == round((85 + 90 + 70) / 3, 1)
    assert ctx["최고"] == 90
    assert ctx["최저"] == 70

def test_build_score_ctx_missing_student():
    ctx = build_score_ctx("신입생", "3MGM", SAMPLE_TEST)
    assert ctx["점수"] == "—"

def test_build_score_ctx_empty_students():
    test_data = {"type": "주간Test", "round": "2", "max_score": 100, "students": {}}
    ctx = build_score_ctx("김철수", "3MGM", test_data)
    assert ctx["평균"] == "—"
    assert ctx["최고"] == "—"
    assert ctx["최저"] == "—"

def test_build_score_ctx_score_zero():
    test_data = {**SAMPLE_TEST, "students": {"김철수": 0, "이영희": 100}}
    ctx = build_score_ctx("김철수", "3MGM", test_data)
    assert ctx["점수"] == 0  # 0 is valid, not "—"

def test_build_score_ctx_type_only():
    test_data = {"type": "기출모의고사", "round": "", "max_score": 100, "students": {}}
    ctx = build_score_ctx("김철수", "3MGM", test_data)
    assert ctx["시험명"] == "기출모의고사"  # trailing space stripped

def test_build_score_ctx_no_type():
    test_data = {"type": "", "round": "3", "max_score": 100, "students": {}}
    ctx = build_score_ctx("김철수", "3MGM", test_data)
    assert ctx["시험명"] == "3"  # leading space stripped


# ── list_variables ───────────────────────────────────────────────────

def test_list_variables_returns_list():
    assert isinstance(list_variables(), list)

def test_list_variables_has_common_and_score():
    vars_ = [v for v, _ in list_variables()]
    assert "{이름}" in vars_
    assert "{점수}" in vars_
    assert "{백분율}" in vars_
