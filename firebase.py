"""
firebase.py — Firebase Realtime Database REST 유틸
Crafted by IDO(idocho@kakao.com) · Powered by Claude AI

ClassManager 가 쓰는 노드 (v2.0 student-centric):
  students/{nameKey}   학생 명단 {name, class}  — read/write (nameKey = 출결번호)
  classes/{classId}    학급 {group, ...}        — read/write
  scores/weekly/       시험 점수                — read-only

dbPath 는 DailyReportWizard 와 공유될 수 있음 (DRW 가 obs/·config/·session/·
input/ 소유, lastSent/는 v2.1.2 폐기). 전체 {dbPath} 노드를 덮어쓰지 말 것 — students/·classes/ 만 write.
"""
import json
import urllib.request
import urllib.error
import urllib.parse


# ── 내부 헬퍼 ────────────────────────────────────────────────────────
def _fb_url(cfg, node):
    """Firebase REST 엔드포인트 생성 (한글 등 자동 URL 인코딩).

    경로는 dbUrl/dbPath 단일 출처만 사용한다. (레거시 firebase_url/firebase_path
    폴백 없음 — 설정이 없으면 조용히 다른 경로로 빠지지 않고 명시적으로 오류.)
    """
    base = (cfg.get('dbUrl') or '').rstrip('/')
    path = (cfg.get('dbPath') or '').strip('/')
    if not base or not path:
        raise ValueError(
            "Firebase 경로가 설정되지 않았습니다. 설정에서 dbUrl·dbPath를 입력하세요."
        )
    enc_path = urllib.parse.quote(path, safe='/')
    enc_node = urllib.parse.quote(node, safe='/')
    url = f"{base}/{enc_path}/{enc_node}.json"
    # Security Rules 전환 대비(#15): dbSecret 설정 시 ?auth= 전달.
    # 미설정이면 종전과 동일(no-op) — 룰 배포 전 운영에 영향 없음.
    secret = (cfg.get('dbSecret') or '').strip()
    if secret:
        url += '?auth=' + urllib.parse.quote(secret, safe='')
    return url


# ── 스키마 버전 게이트 (#15) ─────────────────────────────────────────
SCHEMA_MAX = 14  # DB_SCHEMA v1.4 — 이 클라이언트가 이해하는 스키마 상한


def check_schema(cfg):
    """DB의 schema_version 노드 확인.

    반환 (ok, db_version). 노드 부재·읽기 실패 = (True, None) — 전환 전 DB와
    일시 네트워크 오류에 가용성 우선. 노드값이 SCHEMA_MAX 초과면 (False, v):
    구버전 클라이언트의 신스키마 오염 쓰기를 막아야 하므로 호출측은 차단할 것."""
    try:
        v = firebase_get(cfg, "schema_version")
    except Exception:
        return True, None
    if isinstance(v, int) and v > SCHEMA_MAX:
        return False, v
    return True, v if isinstance(v, int) else None


# ── 기본 CRUD ────────────────────────────────────────────────────────
def firebase_get(cfg, node):
    url = _fb_url(cfg, node)
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read())


def firebase_put(cfg, node, data):
    url     = _fb_url(cfg, node)
    payload = json.dumps(data, ensure_ascii=False).encode('utf-8')
    req     = urllib.request.Request(url, data=payload, method='PUT')
    req.add_header('Content-Type', 'application/json; charset=utf-8')
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read())


def firebase_patch(cfg, node, data):
    url     = _fb_url(cfg, node)
    payload = json.dumps(data, ensure_ascii=False).encode('utf-8')
    req     = urllib.request.Request(url, data=payload, method='PATCH')
    req.add_header('Content-Type', 'application/json; charset=utf-8')
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read())


def firebase_delete(cfg, node):
    url = _fb_url(cfg, node)
    req = urllib.request.Request(url, method='DELETE')
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read())
