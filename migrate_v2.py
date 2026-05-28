"""
migrate_v2.py — Firebase DB 마이그레이션 (구 스키마 → v2.0 신규 스키마)

구 구조 (반 중심):
  config/sheets/{group}/classes/{classId}/students: [{name, ...}]
  obs/{group}|{classId}|{name}|{subject}/{date}: {...}
  input/{group}|{classId}|{name}|{subject}: {...}
  scores/{group}|{classId}/{testKey}/students/{name}: score

신규 구조 (학생 중심):
  students/{nameKey}: {name, class, ...}
  classes/{classId}: {group, courses/{subject}: {textbook, curriculum, instructor}}
  obs/{nameKey}/{subject}/{date}: {...}
  input/{nameKey}/{subject}: {...}
  scores/weekly/{classId}/{subject}/{testKey}/students/{nameKey}: score

실행:
  python migrate_v2.py [--dry-run] [--settings path/to/settings.json]

--dry-run: Firebase에 쓰지 않고 변환 결과만 출력
기존 데이터 삭제 안 함 — 검증 후 수동으로 정리
"""
import json
import sys
import urllib.parse
import urllib.request
import urllib.error
import argparse


# ── Firebase 유틸 ────────────────────────────────────────────────────

def _fb_url(config, node):
    base    = config['firebase_url'].rstrip('/')
    path    = config['firebase_path'].strip('/')
    encoded = urllib.parse.quote(node, safe='/')
    return f"{base}/{path}/{encoded}.json"


def fb_get(config, node):
    url = _fb_url(config, node)
    try:
        with urllib.request.urlopen(urllib.request.Request(url), timeout=15) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        print(f"  [GET 오류] {node}: {e}")
        return None


def fb_put(config, node, data, dry_run=False):
    if dry_run:
        print(f"  [DRY PUT] {node}: {json.dumps(data, ensure_ascii=False)[:120]}")
        return
    url     = _fb_url(config, node)
    payload = json.dumps(data, ensure_ascii=False).encode('utf-8')
    req     = urllib.request.Request(url, data=payload, method='PUT')
    req.add_header('Content-Type', 'application/json; charset=utf-8')
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        print(f"  [PUT 오류] {node}: {e}")


# ── nameKey 생성 ─────────────────────────────────────────────────────

def make_name_key(name, existing_keys):
    """동명이인 처리: "강미주" → "강미주0", "강미주1" ..."""
    if name not in existing_keys:
        existing_keys.add(name)
        return name
    i = 0
    while f"{name}{i}" in existing_keys:
        i += 1
    key = f"{name}{i}"
    existing_keys.add(key)
    return key


# ── 마이그레이션 단계 ────────────────────────────────────────────────

def migrate_students_and_classes(config, dry_run):
    """
    config/sheets/ → students/ + classes/
    반환: {(group, classId, name): nameKey} 매핑 딕셔너리
    """
    print("\n[1/4] 학생 및 반 마이그레이션")
    sheets = fb_get(config, "config/sheets") or {}
    name_map = {}       # (group, classId, name) → nameKey
    existing_keys = set()

    for group, group_data in sheets.items():
        classes = group_data.get("classes", {})
        for class_id, class_data in classes.items():
            # classes/{classId} 노드 생성
            courses = {}
            tb_grade = class_data.get("tb_grade", {})
            textbooks = class_data.get("textbooks", [])
            for tb in textbooks:
                curriculum = tb_grade.get(tb, "")
                courses[tb] = {
                    "textbook": tb,
                    "curriculum": curriculum,
                    "instructor": ""   # 강사는 재배정 필요
                }

            class_node = {"group": group, "courses": courses} if courses else {"group": group}
            fb_put(config, f"classes/{class_id}", class_node, dry_run)
            print(f"  반: {group}/{class_id} → classes/{class_id}")

            # students/{nameKey} 노드 생성
            students = class_data.get("students", [])
            for s in students:
                name = s.get("name", "").strip()
                if not name:
                    continue
                name_key = make_name_key(name, existing_keys)
                name_map[(group, class_id, name)] = name_key

                student_node = {
                    "name": name,
                    "class": class_id,
                }
                if "학번" in s:
                    student_node["학번"] = s["학번"]
                fb_put(config, f"students/{name_key}", student_node, dry_run)
                print(f"  학생: {name} → students/{name_key} (class: {class_id})")

    print(f"  총 {len(name_map)}명 처리")
    return name_map


def migrate_obs(config, name_map, dry_run):
    """
    obs/{group}|{classId}|{name}|{subject}/{date} → obs/{nameKey}/{subject}/{date}
    키 형식: 3분할(group|cls|name) 또는 4분할(group|cls|name|subject)
    """
    print("\n[2/4] obs 마이그레이션")
    obs_data = fb_get(config, "obs") or {}
    migrated = 0
    skipped  = 0

    for raw_key, date_map in obs_data.items():
        decoded = urllib.parse.unquote(raw_key)
        parts   = decoded.split("|")

        if len(parts) == 4:
            group, class_id, name, subject = parts
        elif len(parts) == 3:
            group, class_id, name = parts
            subject = "unknown"
        else:
            print(f"  [스킵] 알 수 없는 키 형식: {decoded}")
            skipped += 1
            continue

        name_key = name_map.get((group, class_id, name))
        if not name_key:
            # 이름 직접 매핑 시도 (group/class 무관)
            for k, v in name_map.items():
                if k[2] == name:
                    name_key = v
                    break

        if not name_key:
            print(f"  [스킵] 학생 미등록: {decoded}")
            skipped += 1
            continue

        if not isinstance(date_map, dict):
            continue

        for date, tag_data in date_map.items():
            fb_put(config, f"obs/{name_key}/{subject}/{date}", tag_data, dry_run)
        migrated += 1
        print(f"  {decoded} → obs/{name_key}/{subject}/ ({len(date_map)}일)")

    print(f"  완료 {migrated}건, 스킵 {skipped}건")


def migrate_input(config, name_map, dry_run):
    """
    input/{group}|{classId}|{name}|{subject} → input/{nameKey}/{subject}
    """
    print("\n[3/4] input 마이그레이션")
    input_data = fb_get(config, "input") or {}
    migrated = 0
    skipped  = 0

    for raw_key, payload in input_data.items():
        decoded = urllib.parse.unquote(raw_key)
        parts   = decoded.split("|")

        if len(parts) == 4:
            group, class_id, name, subject = parts
        elif len(parts) == 3:
            group, class_id, name = parts
            subject = "unknown"
        else:
            print(f"  [스킵] 알 수 없는 키 형식: {decoded}")
            skipped += 1
            continue

        name_key = name_map.get((group, class_id, name))
        if not name_key:
            for k, v in name_map.items():
                if k[2] == name:
                    name_key = v
                    break

        if not name_key:
            print(f"  [스킵] 학생 미등록: {decoded}")
            skipped += 1
            continue

        if not isinstance(payload, dict):
            continue

        fb_put(config, f"input/{name_key}/{subject}", payload, dry_run)
        migrated += 1
        print(f"  {decoded} → input/{name_key}/{subject}")

    print(f"  완료 {migrated}건, 스킵 {skipped}건")


def migrate_scores(config, name_map, dry_run):
    """
    scores/{group}|{classId}/{testKey}/students/{name}
    → scores/weekly/{classId}/{subject}/{testKey}/students/{nameKey}

    subject 추출: testKey 또는 기존 meta에서 시도, 없으면 "unknown"
    """
    print("\n[4/4] scores 마이그레이션")
    scores_data = fb_get(config, "scores") or {}
    migrated = 0
    skipped  = 0

    for raw_cls_key, tests in scores_data.items():
        decoded = urllib.parse.unquote(raw_cls_key)
        parts   = decoded.split("|")

        if len(parts) == 2:
            group, class_id = parts
        else:
            print(f"  [스킵] 알 수 없는 scores 키: {decoded}")
            skipped += 1
            continue

        if not isinstance(tests, dict):
            continue

        for test_key, test_data in tests.items():
            if not isinstance(test_data, dict):
                continue

            meta     = test_data.get("meta", {})
            students = test_data.get("students", {})
            subject  = meta.get("subject", "unknown")

            # nameKey 매핑
            new_students = {}
            for name, score in students.items():
                name_key = name_map.get((group, class_id, name))
                if not name_key:
                    for k, v in name_map.items():
                        if k[2] == name:
                            name_key = v
                            break
                if name_key:
                    new_students[name_key] = score
                else:
                    print(f"    [경고] 학생 미매핑: {name}")

            new_test = {"meta": meta, "students": new_students}
            fb_put(config,
                   f"scores/weekly/{class_id}/{subject}/{test_key}",
                   new_test, dry_run)
            migrated += 1
            print(f"  {decoded}/{test_key} → scores/weekly/{class_id}/{subject}/{test_key}")

    print(f"  완료 {migrated}건, 스킵 {skipped}건")


# ── 메인 ─────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Firebase DB v2.0 마이그레이션")
    parser.add_argument("--dry-run", action="store_true",
                        help="Firebase에 쓰지 않고 결과만 출력")
    parser.add_argument("--settings", default="settings.json",
                        help="settings.json 경로 (기본: ./settings.json)")
    parser.add_argument("--step", choices=["all","students","obs","input","scores"],
                        default="all", help="특정 단계만 실행")
    args = parser.parse_args()

    with open(args.settings, encoding="utf-8") as f:
        config = json.load(f)

    print(f"Firebase: {config['firebase_url']} / {config['firebase_path']}")
    if args.dry_run:
        print("*** DRY RUN 모드 — Firebase 쓰기 없음 ***")

    if args.step in ("all", "students"):
        name_map = migrate_students_and_classes(config, args.dry_run)
    else:
        # 다른 단계만 실행 시 students/ 에서 역매핑 구성
        print("\n[0/4] 기존 students/ 노드에서 name_map 재구성")
        existing = fb_get(config, "students") or {}
        name_map = {}
        for name_key, data in existing.items():
            if isinstance(data, dict):
                name    = data.get("name", name_key)
                class_id = data.get("class", "")
                # group은 classes/에서 조회
                cls_data = fb_get(config, f"classes/{class_id}") or {}
                group    = cls_data.get("group", "M")
                name_map[(group, class_id, name)] = name_key
        print(f"  {len(name_map)}명 로드")

    if args.step in ("all", "obs"):
        migrate_obs(config, name_map, args.dry_run)

    if args.step in ("all", "input"):
        migrate_input(config, name_map, args.dry_run)

    if args.step in ("all", "scores"):
        migrate_scores(config, name_map, args.dry_run)

    print("\n마이그레이션 완료.")
    print("기존 데이터(config/sheets, 구 obs/input/scores)는 삭제하지 않았습니다.")
    print("신규 노드 검증 후 수동으로 정리하세요.")


if __name__ == "__main__":
    main()
