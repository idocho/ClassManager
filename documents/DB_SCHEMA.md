# Firebase DB 스키마 명세

**공유 문서 — ClassManager / DRW2 / DailyReportAnalyzer 공통 참조**  
**문서 버전**: 1.6 · **최종 수정**: 2026-06-12

> v1.6: `scores/trash/` 삭제 스냅샷 노드 신설(시험 삭제 전 자동 백업·관리자 복원). 학년 시험 testKey에서 날짜 제외(`{type}|{round}`), 기출모의고사 weekly 이동, 유형별 기본 만점(성취도평가·반배치고사 150). 추가만 있는 비파괴 개정 — `schema_version` 노드값 불변(14).

> v1.5: `schema_version` 노드 신설(정수, 문서 버전×10 — v1.4 스키마=14). Security Rules 전환 창에 생성. 클라이언트는 기동 시 자기 `SCHEMA_MAX` 초과면 차단(웹/PC DRW/CM) 또는 경고(Analyzer, read-only). 노드 부재·읽기 실패=통과. 모든 클라 REST는 시크릿 설정 시 `?auth={DB Secret}` 부가(미설정=무인증, 전환 전 동작). 절차: DRW `documents/SECURITY_RULES_PLAN.md`. ※ schema_version 값은 이 문서의 "구조 호환성" 버전만 따름 — 문서 표기 수정 등 비파괴 개정은 노드값 불변.
> v1.4: assignments 실형식 정정(객체 배열 {classId,subject,group,role} — 종전 문자열 배열 표기는 오기). lastSent 노드 DB에서 삭제 완료.
> v1.3 (DRW 문서 8.0): `classes/{classId}/courses/{subject}/archived` 신설 — 과목 소프트 삭제. true면 보관 과목(표시/입력/전송 제외, obs·scores·history 기록 보존, 같은 키 재추가 시 복원). 과목 쓰기는 노드 단위 PATCH만 — **classes 전체 PUT 금지**(stale 클라이언트가 삭제 과목을 되살리는 부활 버그 방지).
> v1.2 (DRW v2.1.2): `input/` 특이사항 학생 단위 단일(`__note__`)로, 과제수행도는 `obs/assign_grade` 단일 소스(`input/.assign` 폐기). `history/{nameKey}/{date}` 신규(전송 코멘트 누적). `lastSent/` 폐기.

---

## 1. Firebase 노드 구조

```
root/
├── students/
│   └── {nameKey}/                  # 출결번호 = Firebase 키 (불변 고유번호, 예: "20240012")
│       ├── name: "강미주"           # 실제 표시 이름 (변경 가능)
│       └── class: "3MAM"           # 현재 반 참조 (null = 무소속)
│
├── classes/
│   └── {classId}/                  # 반 식별자 (예: "3MAM", "2TGF")
│       ├── group: "M"              # 요일 그룹: M=월수금, T=화목토
│       └── courses/
│           └── {subject}/          # 과목 식별자 (예: "3-1", "3-2")
│               ├── textbook: "최상위수학"       # 순수 책 이름 (과정 정보 미포함)
│               ├── curriculum: "middle_school.grade_3.semester_1"  # curriculum.js 키
│               ├── instructor: "강사ID"         # 담당 강사 ID
│               └── archived: true              # (선택, v1.3) 소프트 삭제 — 보관 과목.
│                                               #   표시/입력/전송 제외, 기록(obs·scores·history) 보존.
│                                               #   같은 키 재추가 시 archived:null로 복원
│
├── obs/
│   └── {nameKey}/
│       └── {subject}/
│           └── {YYYY-MM-DD}/       # 날짜별 관찰 기록
│               ├── condition: "great"|"good"|"normal"|"low"|"bad"
│               ├── understand: "top"|"good"|"normal_u"|"confused"|"hard"
│               ├── understand_sub: []
│               ├── engage: []
│               ├── caution: []
│               ├── extra: []
│               ├── highlight: []
│               ├── assign_grade: "done"|"most"|"half"|"little"|"none"  # 과제수행도 단일 소스 (DRW v2.1.2)
│               └── assign_tags: []
│
├── input/                          # 당일 입력 (휘발). DRW v2.1.2: 특이사항만, 학생 단위
│   └── {nameKey}/
│       └── __note__/
│           └── note: "..."         # 특이사항 (학생 단위 단일, 과목 종속 아님)
│                                   # (구 {subject}/{assign,note} 폐기 — 마이그레이션으로 __note__ 통합)
│
├── scores/
│   ├── weekly/
│   │   └── {classId}/
│   │       └── {subject}/
│   │           └── {testKey}/      # 형식: "{YYYY-MM-DD}|{type}|{round}"
│   │               ├── meta/
│   │               │   ├── date: "YYYY-MM-DD"
│   │               │   ├── max_score: 100
│   │               │   └── type: "주간Test"|"직접입력"|...
│   │               └── students/
│   │                   └── {nameKey}: 85
│   │
│   ├── achievement/
│   │   └── {curriculum}/           # curriculum.js 키 (점 → 언더스코어 치환)
│   │       └── {testKey}/          # 형식: "{type}|{round}" — 날짜 미포함(반·학생별 시행일 상이 허용, DRW v8.23)
│   │           ├── meta/
│   │           │   ├── date: "YYYY-MM-DD"   # 대표 시행일(마지막 저장 기준)
│   │           │   ├── max_score: 150       # 성취도평가·반배치고사 기본 150, 그 외 100
│   │           │   ├── round: 1
│   │           │   └── type: "성취도평가"|"반배치고사"|"실전모의고사"   # 기출모의고사는 weekly로 이동(v8.20)
│   │           └── students/
│   │               └── {nameKey}: 92        # 과정 수강생 전체 코호트 (반 무관)
│   │
│   └── trash/                      # (v1.6) 삭제 스냅샷 — 시험 삭제 전 자동 백업, 관리자 복원 UI(DRW 웹)
│       └── {ts}_{testKeySafe}/
│           ├── path: "scores/weekly/..|scores/achievement/.."   # 원 경로
│           ├── testKey, reason, deletedAt(ISO), by
│           └── test/ {meta, students}       # 삭제 시점 전체 노드
│
├── config/
│   └── instructors/
│       └── {instructorId}/
│           ├── name: "홍길동"
│           ├── assignments:                # 객체 배열 — 실제 웹 저장 형식 (v1.4 정정)
│           │   └── [{classId: "3MAM", subject: "중3-1 SIGNATURE 100+", group: "M", role: "담임"}]
│           │       # role: 담임|부담임 · 구형 키(sheet/cls/tb)는 PC 폴백만
│           └── presets: []
│
├── session/
│   └── class_data/                 # 진도/과제 (DRW2 PC 앱 사용, 휘발)
│
├── history/                        # 전송된 최종 특이사항 누적 (DRW v2.1.2 신규)
│   └── {nameKey}/
│       └── {YYYY-MM-DD}/           # 학생·날짜별 (같은 날 재전송 시 덮어씀)
│           ├── note: "..."         # 전송 확정 시점의 최종 코멘트
│           └── instructor: "강사ID"
│
├── schema_version: 14              # (v1.5) 정수 = 문서 버전×10. Security Rules 전환 창에 생성.
│                                   #   클라 SCHEMA_MAX 초과 → 차단(웹/PC/CM)·경고(Analyzer). 부재=통과
│
└── (lastSent/ — DRW v2.1.2 폐기)
```

---

## 2. 변수명 규칙

| 변수 | 설명 | 예시 값 |
|------|------|---------|
| `nameKey` | 학생 식별자 = 출결번호 (불변) | `"20240012"`, `"20240013"` |
| `classId` | 반 식별자 | `"3MAM"`, `"2TGF"` |
| `group` | 요일 그룹 | `"M"` (월수금), `"T"` (화목토) |
| `subject` | 과목 식별자 (반 내) | `"3-1"`, `"3-2"` |
| `curriculum` | 커리큘럼 키 (curriculum.js) | `"middle_school.grade_3.semester_1"` |
| `testKey` | 시험 키 | `"2026-05-27\|주간Test\|3"` |
| `instructorId` | 강사 식별자 | `"홍길동"` |
| `config` | 로컬 설정 객체 | `{dbUrl, dbPath, ...}` |
| `dbUrl` | Firebase URL | `"https://....firebaseio.com"` |
| `dbPath` | Firebase 루트 경로 | `"drw_xxxxxxxx"` |

---

## 3. 코드 변수명 매핑 (구 → 신)

| 구 변수명 | 신 변수명 | 비고 |
|----------|----------|------|
| `sheet` / `sh` | `group` | M=월수금, T=화목토 |
| `cls` | `classId` | `class`는 예약어 |
| `tb` | `subject` | 과목 식별자 |
| `cfg` | `config` | 단축어 제거 |
| `okey` | 제거 | 구 복합키 불필요 |
| `fb_config` | `classData` | Firebase config 캐시 |
| `fb_scores` | `scoreData` | |
| `fbUrl` / `fbPath` | `dbUrl` / `dbPath` | |
| `curSheet` | `activeGroup` | |
| `curNav` | `activeTab` | |
| `src_sh` / `dst_sh` | `sourceGroup` / `targetGroup` | |
| `src_cls` / `dst_cls` | `sourceClassId` / `targetClassId` | |
| `sts` | `students` | |

---

## 4. 성적 입력 권한

| 시험 종류 | 노드 | 입력 권한 |
|----------|------|----------|
| 반별 주간 시험 | `scores/weekly/{classId}/{subject}/` | 담당 수업 배정(`assignments`에 해당 반+과목) — DRW v2.2.3에서 instructor 필드 기준 폐기 |
| 학년단위 시험 | `scores/achievement/{curriculum}/` | 담임 (`assignments`에 해당 반 포함) |

---

## 5. 학생 상태 정책

| 상황 | 동작 |
|------|------|
| 반 삭제 | 학생 `class` 필드 → `null` (무소속 잔류) |
| 학생 삭제 | `students/{nameKey}` 완전 삭제. `obs/`, `input/`, `history/`, `scores/.../students/{nameKey}` 수동 정리 필요 |
| 학생 반 이동 | `students/{nameKey}/class` 필드만 변경 (1 write). obs/input/history 이관 불필요 |
| 무소속 학생 | ClassManager 전용 UI에서 반 배정 또는 삭제 |

---

## 6. curriculum.js 키 규칙

Firebase 키에 `.` 사용 불가 → `scores/achievement/` 노드에서는 `.`을 `_`로 치환.

```
curriculum.js 키:  "middle_school.grade_3.semester_1"
Firebase 노드 키:  "middle_school_grade_3_semester_1"
```

앱 코드에서 변환 유틸리티 사용:
```js
const toCurriculumKey = (c) => c.replaceAll('.', '_');
const fromCurriculumKey = (k) => k.replaceAll('_', '.');
```
