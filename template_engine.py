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


def build_score_ctx(name: str, cls: str, test_data: dict) -> dict:
    ctx = build_common_ctx(name, cls)
    students = test_data.get("students", {})
    scores = [v for v in students.values() if isinstance(v, (int, float))]
    my_score = students.get(name)

    ctx.update({
        "시험명": f"{test_data.get('type', '')} {test_data.get('round', '')}".strip(),
        "점수":   my_score if my_score is not None else "—",
        "만점":   test_data.get("max_score", 100),
        "평균":   round(sum(scores) / len(scores), 1) if scores else "—",
        "최고":   max(scores) if scores else "—",
        "최저":   min(scores) if scores else "—",
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
