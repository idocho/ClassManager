# Firebase DB 스키마 명세

**공유 문서 — ClassManager / DRW2 / DailyReportAnalyzer 공통 참조**  
**문서 버전**: 1.3 · **최종 수정**: 2026-06-10

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
│   └── achievement/
│       └── {curriculum}/           # curriculum.js 키 (점 → 언더스코어 치환)
│           └── {testKey}/
│               ├── meta/
│               │   ├── date: "YYYY-MM-DD"
│               │   ├── max_score: 100
│               │   ├── round: 1
│               │   └── type: "성취도평가"|"기출모의고사"|...
│               └── students/
│                   └── {nameKey}: 92
│
├── config/
│   └── instructors/
│       └── {instructorId}/
│           ├── name: "홍길동"
│           ├── assignments: ["3MAM|3-1", "3MAM|3-2"]   # classId|subject
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
| 반별 주간 시험 | `scores/weekly/{classId}/{subject}/` | 해당 subject의 `instructor` |
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
