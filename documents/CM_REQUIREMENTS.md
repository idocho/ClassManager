# ClassManager — 요구사항 명세서

**Crafted by IDO(idocho@kakao.com) · Powered by Claude AI**  
**문서 버전**: 2.1 · **최종 수정**: 2026-05-28

> Firebase 스키마: [DB_SCHEMA.md](./DB_SCHEMA.md) 참조

---

## 변경 이력

| 버전 | 날짜 | 내용 |
|------|------|------|
| 1.0 | 2026-05-24 | 최초 작성 (KakaoTalk Blaster → ClassManager 리팩토링) |
| 2.0 | 2026-05-27 | DB 구조 전면 재설계 (반 중심 → 학생 중심). 변수명 일괄 변경. 무소속 학생 관리 UI 추가 |
| 2.1 | 2026-05-28 | nameKey = 출결번호 (불변 고유번호). 이름 기반 키 + 동명이인 suffix 로직 폐기. CSV export 컬럼 변경 |

---

## 1. 프로젝트 개요

### 1.1 목적

수학학원 관리자(admin)가 학생·반 데이터를 관리하고, KakaoTalk 일괄 발송(공지/성적통지)을 수행하는 데스크탑 도구.

### 1.2 구성 파일

| 파일 | 역할 |
|------|------|
| `main.py` | 진입점 |
| `app.py` | 전체 GUI 및 비즈니스 로직 |
| `firebase.py` | Firebase REST CRUD |
| `kakao_send.py` | KakaoTalk 자동화 (pyautogui/pyperclip) |
| `template_engine.py` | 메시지 템플릿 `{변수}` 치환 |
| `import_roster.py` | 학생 명단 등록 |
| `settings.json` | 로컬 설정 (dbUrl, dbPath, wait_time, room_prefix) |
| `templates.json` | 메시지 템플릿 (로컬 저장) |

### 1.3 실행 환경

```bash
pip install -r requirements.txt
python main.py
```

KakaoTalk PC 앱 설치 및 로그인 필요. `pyautogui`/`pyperclip` 없으면 발송 버튼 비활성화.

---

## 2. 역할 및 권한

ClassManager = **관리자 전용 도구**.

| 기능 | 관리자 |
|------|--------|
| 학생 등록 / 삭제 / 반 배정 | ✅ |
| 반 생성 / 삭제 / 수정 | ✅ |
| 무소속 학생 관리 | ✅ |
| 성적 조회 | ✅ (읽기) |
| KakaoTalk 일괄공지 / 성적통지 발송 | ✅ |
| 교재 등록/관리 | ❌ (DRW2 강사 권한) |
| 일일보고서 발송 | ❌ (DRW2 담임 권한) |

---

## 3. 기능 명세

### 3.1 학생 관리

**등록**
- 출결번호 입력 (필수) → `students/{출결번호}` = nameKey로 노드 생성
- 이름 입력 (표시용, 변경 가능)
- 반 선택 → `students/{nameKey}/class` 설정
- 동명이인 문제 없음 — 출결번호가 고유 키이므로 suffix 로직 불필요

**삭제**
- 확인 다이얼로그 표시
- `students/{nameKey}` 노드 완전 삭제
- 해당 학생의 `obs/`, `input/` 노드 cascade 삭제

**반 이동**
- 대상 반 선택 → `students/{nameKey}/class` 필드 단일 write
- obs/input 데이터 이관 불필요 (학생 키 기반이므로 자동 유지)

### 3.2 반 관리

**생성**
- 반 이름, group(M/T) 선택 → `classes/{classId}` 노드 생성

**삭제**
- 확인 다이얼로그: "소속 학생은 무소속으로 잔류합니다" 안내
- `classes/{classId}` 삭제
- 소속 학생 전체 → `students/{nameKey}/class = null`

**수정**
- 반 이름 변경: 노드 이동 + `scores/weekly/{classId}` 이동

### 3.3 무소속 학생 관리

- 별도 탭 또는 섹션: `class == null`인 학생 목록 표시
- 각 학생 행: 이름, 출결번호(nameKey), [반 배정] [삭제] 버튼
- 반 배정 → `students/{nameKey}/class` 업데이트

### 3.4 성적 조회

- 반 + 과목(subject) 선택 → `scores/weekly/{classId}/{subject}/` 로드
- 학년단위 시험: `scores/achievement/{curriculum}/` 로드
- 읽기 전용 (입력은 DRW2)

### 3.5 KakaoTalk 발송

**공통 발송 흐름**
1. 반 + 학생 선택
2. 템플릿 선택 (common / score 타입)
3. score 타입: 시험 선택 → 학생별 점수 자동 치환
4. KakaoTalk 자동화 실행 (3초 대기 후 시작)

**send_messages 순서** (`kakao_send.py`)
- 룸명 복사 → Ctrl+F → Esc → Ctrl+F → 붙여넣기 → Enter
- 메시지 복사 → 붙여넣기 → Enter → Esc

**발송 유형**
- 일괄공지: 단일 공통 메시지 → 반 전체 발송
- 성적통지: 개인별 점수 치환 메시지 발송

---

## 4. Firebase 연동

### 4.1 읽기 노드

| 노드 | 용도 |
|------|------|
| `students/` | 학생 목록 전체 |
| `classes/` | 반 목록 및 과목 정보 |
| `scores/weekly/{classId}/{subject}/` | 반별 시험 성적 |
| `scores/achievement/{curriculum}/` | 학년단위 시험 성적 |
| `config/instructors/` | 강사 정보 |

### 4.2 쓰기 노드

| 노드 | 동작 |
|------|------|
| `students/{nameKey}` | 학생 생성/수정/삭제 |
| `classes/{classId}` | 반 생성/수정/삭제 |

### 4.3 주요 경로 변환 (구 → 신)

| 구 경로 | 신 경로 |
|---------|---------|
| `config/sheets/{group}/classes/{classId}/students` | `students/` (전체) + `classes/{classId}` |
| `scores/{group}\|{classId}/{testKey}/students/{name}` | `scores/weekly/{classId}/{subject}/{testKey}/students/{nameKey}` |
| `obs/{group}\|{classId}\|{name}\|{subject}/{date}` | `obs/{nameKey}/{subject}/{date}` |

---

## 5. UI 구성 (탭)

| 탭 | 내용 |
|----|------|
| 명단 관리 | 반 목록, 학생 목록, CRUD 버튼 |
| 무소속 학생 | 미배정 학생 목록, 반 배정/삭제 |
| 성적 조회 | 반/과목 선택, 시험 목록, 점수표 |
| 발송 | 반/학생 선택, 템플릿, 발송 실행 |
| 설정 | dbUrl, dbPath, wait_time, room_prefix |

---

## 6. 스레딩 모델

Firebase 호출 및 KakaoTalk 발송 루프는 `threading.Thread(daemon=True)` 실행.  
UI 업데이트는 반드시 `self.root.after(0, callback)` 경유.

---

## 7. 스코프 제외

| 항목 | 사유 |
|------|------|
| 교재 등록/관리 | DRW2 강사 권한 |
| obs/input 입력 | DRW2 강사 권한 |
| 일일보고서 발송 | DRW2 담임 권한 |
| 학년단위 성적 입력 | DRW2 담임 권한 |
