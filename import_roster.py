"""
import_roster.py — 재원생.xlsx → Firebase config/sheets 업로드

사용법:
    python import_roster.py [--dry-run]

--dry-run: Firebase 업로드 없이 결과만 출력
"""
import json
import re
import sys
import openpyxl

from firebase import firebase_put


XLSX_PATH = "src/재원생.xlsx"
SHEET_NAME = "Sheet1"
COL_STUDENT_ID = 0   # 학생ID
COL_CLASS      = 7   # 수업반

KOREAN_NAME_RE = re.compile(r'^[가-힣]{2,4}(,\s*[가-힣]{2,4})*$')
TRAILING_DIGIT_RE = re.compile(r'\d+$')
SEMESTER_PREFIX_RE = re.compile(r'^26(?:SP|SU)?\s+')


def normalize(cls_name: str) -> str:
    return SEMESTER_PREFIX_RE.sub('', cls_name).strip()


def classify(cls_name: str) -> str | None:
    """반 이름 → 'M' | 'T' | None(무시)"""
    if 'MAXIMO' in cls_name:
        return 'M'
    if '개별' in cls_name:
        return 'T'
    if cls_name.endswith('M'):
        return 'M'
    if cls_name.endswith('T'):
        return 'T'
    return None


def extract_name(student_id: str) -> str:
    return TRAILING_DIGIT_RE.sub('', student_id.strip())


def parse_classes(cell_value) -> list[str]:
    if not cell_value or str(cell_value).strip() == '-':
        return []
    result = []
    for token in str(cell_value).split(';'):
        token = token.strip()
        if not token:
            continue
        if KOREAN_NAME_RE.match(token):
            continue
        result.append(token)
    return result


def build_sheets(ws) -> dict:
    sheets: dict[str, dict[str, list]] = {'M': {}, 'T': {}}
    skipped_classes: set[str] = set()

    for row in ws.iter_rows(min_row=2, values_only=True):
        student_id = row[COL_STUDENT_ID]
        class_cell = row[COL_CLASS]
        if not student_id:
            continue
        name = extract_name(str(student_id))
        if not name:
            continue

        for cls in parse_classes(class_cell):
            sheet = classify(cls)
            if sheet is None:
                skipped_classes.add(cls)
                continue
            cls = normalize(cls)
            bucket = sheets[sheet].setdefault(cls, [])
            if not any(s['name'] == name for s in bucket):
                bucket.append({'name': name})

    return sheets, skipped_classes


def main():
    dry_run = '--dry-run' in sys.argv

    with open('settings.json', encoding='utf-8') as f:
        cfg = json.load(f)

    wb = openpyxl.load_workbook(XLSX_PATH)
    ws = wb[SHEET_NAME]

    sheets, skipped = build_sheets(ws)

    total_m = sum(len(v) for v in sheets['M'].values())
    total_t = sum(len(v) for v in sheets['T'].values())

    print(f"[M] {len(sheets['M'])}개 반, {total_m}명")
    for cls, students in sorted(sheets['M'].items()):
        print(f"    {cls}: {len(students)}명")

    print(f"[T] {len(sheets['T'])}개 반, {total_t}명")
    for cls, students in sorted(sheets['T'].items()):
        print(f"    {cls}: {len(students)}명")

    if skipped:
        print(f"\n[SKIP] {len(skipped)}개 반 무시:")
        for c in sorted(skipped):
            print(f"    {c}")

    if dry_run:
        print("\n--dry-run: Firebase 업로드 생략")
        return

    payload = {
        sheet: {'classes': {cls: {'students': students}
                            for cls, students in classes.items()}}
        for sheet, classes in sheets.items()
    }

    print("\nFirebase 업로드 중...")
    firebase_put(cfg, 'config/sheets', payload)
    print(f"완료: M {len(sheets['M'])}반 / T {len(sheets['T'])}반 업로드")


if __name__ == '__main__':
    main()
