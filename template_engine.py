"""
template_engine.py — 메시지 템플릿 {변수} 치환 엔진
Crafted by IDO(idocho@kakao.com)

지원 변수:
  공통: {이름} {반} {날짜}
  성적: {시험명} {점수} {만점} {평균} {최고} {최저} {백분율}
"""
import datetime
import re


def render(template: str, ctx: dict) -> str:
    """ctx 키로 {변수} 치환. 미정의 변수는 그대로 유지."""
    def replacer(m):
        key = m.group(1)
        return str(ctx.get(key, m.group(0)))
    return re.sub(r'\{([^}]+)\}', replacer, template)


def build_common_ctx(name: str, cls: str) -> dict:
    today = datetime.date.today()
    return {
        "이름": name,
        "반": cls,
        "날짜": f"{today.month}/{today.day}",
    }


def _num(v):
    """점수 값 숫자화 — int/float/숫자 문자열 허용, 그 외 None (웹 입력은 문자열일 수 있음)."""
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        try:
            return float(v.strip())
        except ValueError:
            return None
    return None


def build_score_ctx(name: str, cls: str, test_data: dict, name_key: str = None) -> dict:
    """v2.0 스키마 대응:
    - students/ 키는 nameKey(출결번호) — name_key 우선 조회, 구 스키마(이름 키) 폴백
    - 시험 정보(type/round/date/max_score)는 meta/ 하위 — 평면 구조 폴백
    """
    ctx = build_common_ctx(name, cls)
    meta = test_data.get("meta", test_data)
    students = test_data.get("students", {})
    scores = [n for n in (_num(v) for v in students.values()) if n is not None]
    my_score = _num(students.get(name_key)) if name_key is not None else None
    if my_score is None:
        my_score = _num(students.get(name))   # 구 스키마(이름 키) 데이터 폴백

    def _fmt(n):
        return int(n) if n == int(n) else round(n, 1)

    ctx.update({
        "시험명": f"{meta.get('type', '')} {meta.get('round', '')}".strip(),
        "점수":   _fmt(my_score) if my_score is not None else "—",
        "만점":   meta.get("max_score", 100),
        "평균":   round(sum(scores) / len(scores), 1) if scores else "—",
        "최고":   _fmt(max(scores)) if scores else "—",
        "최저":   _fmt(min(scores)) if scores else "—",
        "백분율": _percentile(my_score, scores),
    })
    return ctx


def _percentile(score, scores):
    if score is None or not isinstance(score, (int, float)) or not scores:
        return "—"
    if len(scores) == 1:
        return 100
    below = sum(1 for s in scores if s < score)
    return round(below / (len(scores) - 1) * 100)


def list_variables() -> list:
    """UI 힌트용 변수 목록."""
    return [
        ("{이름}", "학생 이름"),
        ("{반}",   "학급명"),
        ("{날짜}", "오늘 날짜 (M/D)"),
        ("{시험명}", "시험 유형+회차 [성적]"),
        ("{점수}",  "학생 점수 [성적]"),
        ("{만점}",  "최대 점수 [성적]"),
        ("{평균}",  "반 평균 [성적]"),
        ("{최고}",  "반 최고점 [성적]"),
        ("{최저}",  "반 최저점 [성적]"),
        ("{백분율}", "반 내 백분율 [성적]"),
    ]
