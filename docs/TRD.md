# peTox 기술요구사항정의서 (Technical Requirements Document)

**문서 버전**: 1.0  
**작성일**: 2026-09-04  
**최종 제출일**: 2026-10-01  
**팀**: 최수빈(PM/디자인), 김민형(BE), 박민규(FE), 박현식(AI)

---

## 1. 개요

### 1.1 프로젝트 정의
**peTox**는 Android 전용 모바일 앱으로, 사용자가 양육하는 가상 반려동물을 통해 숏폼 동영상 앱(틱톡, 인스타그램 릴스, 유튜브 쇼츠) 사용 시간을 자발적으로 줄이도록 유도하는 디지털 웰빙 애플리케이션입니다.

### 1.2 핵심 기능
- **온보딩**: 일일 목표 시간 설정, 반려동물 사진 → 픽셀 캐릭터 변환 등록
- **홈 대시보드**: 캐릭터 상태, 오늘의 사용 시간, 진행 중인 미션 표시
- **오버레이 기능**: 사용자가 제한 앱 사용 시 캐릭터가 화면 위에 등장하여 단계적으로 확대 및 햅틱 피드백 제공
- **캐릭터 성장**: 미션 달성 시 획득한 코인으로 캐릭터 레벨 상승 및 아이템 구매
- **주간 리포트**: 지난주 vs 이번주 앱 사용 시간 비교 분석
- **상점**: 캐릭터 의상, 추가 펫 슬롯 구매

### 1.3 기대 효과
- 사용자의 자발적 숏폼 콘텐츠 시청 감소
- 집중력 향상 및 수면 개선
- 반려동물 양육이라는 재미를 통한 행동 변화 유도

---

## 2. 시스템 아키텍처

### 2.1 전체 구성도
```
┌─────────────────────────────────────────────────────────────┐
│                     React Native App (Android)               │
│  ┌──────────────────────────────────────────────────────┐   │
│  │ Frontend (박민규)                                     │   │
│  │ - 온보딩, 홈, 오버레이, 캐릭터, 리포트, 상점 화면   │   │
│  │ - ML Kit Subject Segmentation 통합 (온디바이스)     │   │
│  │ - UsageStatsManager, AccessibilityService 연동      │   │
│  └──────────────────────────────────────────────────────┘   │
│                              ↓                                 │
│  ┌──────────────────────────────────────────────────────┐   │
│  │ Android System Features (박현식)                      │   │
│  │ - SYSTEM_ALERT_WINDOW: 다른 앱 위에 오버레이 표시   │   │
│  │ - UsageStatsManager: 앱 사용 시간 감지              │   │
│  │ - AccessibilityService: 앱 전환 이벤트 감지         │   │
│  │ - ML Kit: 반려동물 사진 배경 제거 (온디바이스)      │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
                              ↕ HTTP/HTTPS
                    (FastAPI REST API)
┌─────────────────────────────────────────────────────────────┐
│                   FastAPI Backend (BE)                       │
│  ┌──────────────────────────────────────────────────────┐   │
│  │ API Layer (김민형)                                    │   │
│  │ - /auth: 가입, 인증                                  │   │
│  │ - /profiles: 사용자 프로필 관리                      │   │
│  │ - /pets: 반려동물 CRUD                              │   │
│  │ - /usage-logs: 앱 사용 로그 기록                     │   │
│  │ - /missions: 미션 조회, 완료 처리                    │   │
│  │ - /coins: 코인 거래 내역                            │   │
│  │ - /items: 상점 아이템 조회, 구매                     │   │
│  │ - /reports: 주간 리포트 생성                        │   │
│  └──────────────────────────────────────────────────────┘   │
│                              ↓                                 │
│  ┌──────────────────────────────────────────────────────┐   │
│  │ Business Logic Layer                                  │   │
│  │ - 미션 로직: 사용 시간 기준으로 완료 판정            │   │
│  │ - 보상 로직: 미션 완료 → 코인 지급                   │   │
│  │ - 오버레이 트리거: 사용 시간 초과 시점 계산         │   │
│  │ - 리포트 생성: 주간 통계 집계                       │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
                              ↕
┌─────────────────────────────────────────────────────────────┐
│                      Data Layer                              │
│  ┌──────────────────────────────────────────────────────┐   │
│  │ PostgreSQL (Supabase)                                │   │
│  │ - 11개 테이블 (profiles, pets, usage_logs 등)       │   │
│  │ - Supabase Auth (JWT 기반 인증)                      │   │
│  │ - Real-time subscriptions 미지원 (단방향 REST)      │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 데이터 흐름

**사용자 온보딩 흐름**:
1. 회원가입 (이메일/비번) → Supabase Auth
2. 반려동물 사진 촬영 → ML Kit 배경 제거 (온디바이스) → 픽셀 이미지 변환
3. 일일 목표 설정 → profiles 테이블 저장

**일일 앱 사용 감지 흐름**:
1. UsageStatsManager 또는 AccessibilityService가 틱톡/인스타/유튜브 시청 감지
2. 사용 시간이 누적되면 usage_logs에 기록
3. 백엔드가 주기적으로 로그를 조회하여 미션 진행 상황 업데이트
4. 목표 시간 초과 시 → 오버레이 트리거 신호 → 앱에서 캐릭터 표시

**코인 및 보상 흐름**:
1. 미션 완료 → coin_ledger에 기록
2. user_items에서 구매 기록
3. 캐릭터 레벨 상승 및 아이템 장착

---

## 3. 기술 스택

| 계층 | 기술 | 상세 |
|------|------|------|
| **프론트엔드** | React Native | Android 전용, Expo 또는 bare workflow |
| **UI/UX** | React Native Gesture Handler, Reanimated | 오버레이 애니메이션, 햅틱 |
| **이미지 처리** | ML Kit Subject Segmentation | 온디바이스, 외부 AI API 미사용 |
| **백엔드** | FastAPI | Python 3.10+, 비동기 지원 |
| **ORM** | SQLAlchemy 2.0+ | PostgreSQL 드라이버 (psycopg) |
| **인증** | Supabase Auth | JWT 토큰 기반 |
| **데이터베이스** | PostgreSQL 15+ (Supabase) | 11개 테이블, 사용자 격리 |
| **API 명세** | OpenAPI 3.1 (FastAPI 자동 생성) | /docs 경로에서 Swagger UI 제공 |
| **배포** | AWS (예정) 또는 Heroku | Docker 컨테이너화 |
| **안드로이드 API** | UsageStatsManager, AccessibilityService, SYSTEM_ALERT_WINDOW | API 레벨 29+ |
| **의존성 관리** | pip + requirements.txt | Python 패키지 |

---

## 4. API 명세

### 4.1 현재 구현 상태

#### 4.1.1 헬스 체크
```http
GET /health
```
**응답**:
```json
{"status": "ok"}
```
**목적**: 서버 상태 확인

---

#### 4.1.2 데이터베이스 헬스 체크
```http
GET /db-health
```
**응답**:
```json
{"db": "ok"}
```
**목적**: DB 연결 상태 확인

---

#### 4.1.3 아이템 조회 (임시 구현)
```http
GET /items/{item_id}?q={query}
```
**요청 매개변수**:
- `item_id` (path, int): 아이템 ID
- `q` (query, str, optional): 추가 쿼리

**응답**:
```json
{
  "item_id": 1,
  "q": "example"
}
```
**목적**: 상점 아이템 조회 (현재는 임시 응답)

---

#### 4.1.4 회원가입
```http
POST /auth/signup
Content-Type: application/json

{
  "email": "user@example.com",
  "password": "password123"
}
```
**응답 (성공)**:
```json
{
  "user_id": "550e8400-e29b-41d4-a716-446655440000"
}
```
**응답 (실패)**:
```json
{
  "detail": "User already exists"
}
```
**목적**: 사용자 계정 생성 및 Supabase Auth에 등록

---

### 4.2 향후 확장 필요 엔드포인트

| 기능 | 메서드 | 경로 | 상태 |
|------|--------|------|------|
| 로그인 | POST | `/auth/login` | 필수 |
| 로그아웃 | POST | `/auth/logout` | 필수 |
| 프로필 조회 | GET | `/profiles/{user_id}` | 필수 |
| 프로필 수정 | PUT | `/profiles/{user_id}` | 필수 |
| 반려동물 목록 | GET | `/pets?user_id={user_id}` | 필수 |
| 반려동물 생성 | POST | `/pets` | 필수 |
| 반려동물 수정 | PUT | `/pets/{pet_id}` | 필수 |
| 반려동물 삭제 | DELETE | `/pets/{pet_id}` | 선택 |
| 사용 로그 기록 | POST | `/usage-logs` | 필수 |
| 사용 로그 조회 | GET | `/usage-logs?user_id={user_id}&date={date}` | 필수 |
| 미션 조회 | GET | `/missions?user_id={user_id}&type={daily\|weekly}` | 필수 |
| 미션 완료 | PUT | `/missions/{mission_id}/complete` | 필수 |
| 코인 조회 | GET | `/coins/{user_id}` | 필수 |
| 코인 거래 내역 | GET | `/coins/{user_id}/history` | 필수 |
| 상점 아이템 목록 | GET | `/items` | 필수 |
| 아이템 상세 | GET | `/items/{item_id}` | 필수 |
| 아이템 구매 | POST | `/items/{item_id}/purchase` | 필수 |
| 주간 리포트 | GET | `/reports/{user_id}?week={YYYYWW}` | 필수 |
| 알림 설정 | PUT | `/notification-settings/{user_id}` | 선택 |

### 4.3 API 응답 형식

모든 API는 다음 형식을 따릅니다:

**성공 (2xx)**:
```json
{
  "data": {...},
  "status": "success"
}
```

**에러 (4xx, 5xx)** (현재는 FastAPI 기본 HTTPException 사용):
```json
{
  "detail": "Error message"
}
```

---

## 5. 데이터베이스 스키마

### 5.1 테이블 개요

| # | 테이블명 | 주요 컬럼 | 목적 |
|---|----------|---------|------|
| 1 | `profiles` | id, goal_minutes, focus_start, focus_end, bedtime, pet_slot_limit | 사용자 프로필 및 설정 |
| 2 | `pets` | id, user_id, name, source_photo_url, pixel_image_url, level, affection | 반려동물 캐릭터 |
| 3 | `detected_apps` | id, package_name, display_name | 감지 대상 앱 (틱톡, 인스타, 유튜브) |
| 4 | `user_detected_apps` | user_id, app_id, is_enabled | 사용자별 감지 앱 설정 |
| 5 | `usage_logs` | id, user_id, app_id, started_at, ended_at, duration_seconds | 앱 사용 로그 |
| 6 | `missions` | id, type, title, target_minutes, reward_coins, valid_date | 미션 템플릿 |
| 7 | `user_missions` | id, user_id, mission_id, status, coins_earned, completed_at | 사용자 미션 진행 상황 |
| 8 | `coin_ledger` | id, user_id, pet_id, amount, reason, created_at | 코인 거래 내역 |
| 9 | `items` | id, name, type, price_coins, image_url | 상점 아이템 (의상, 펫 슬롯) |
| 10 | `user_items` | id, user_id, item_id, purchased_at, is_equipped | 사용자 보유 아이템 |
| 11 | `notification_settings` | user_id, mission_alert, report_alert | 알림 설정 |

### 5.2 FK 및 인덱스
- **FK**: auth.users와의 계층적 연결 (ON DELETE CASCADE)
- **인덱스**: user_id, app_id, pet_id 등 주요 조회 컬럼에 생성
- **제약**: type ENUM 검사, unique 제약 (user_id + app_id, user_id + mission_id 등)

### 5.3 데이터 무결성
- **자동 타임스탐프**: created_at, updated_at (별도 명시 필요)
- **기본값**: pet_slot_limit=1, affection=0, is_enabled=true 등
- **Cascade 삭제**: 사용자 삭제 시 관련 모든 데이터 자동 삭제

---

## 6. 안드로이드 특화 기술 요구사항

### 6.1 앱 사용 시간 감지

**UsageStatsManager** (권장):
- API 레벨 21+
- 권한: `PACKAGE_USAGE_STATS`
- 장점: 정확한 포그라운드 앱 시간 추적, 배터리 효율적
- 제한: 2시간 단위 캐시 → 실시간 감지 불가 (AccessibilityService 병행 필요)

**AccessibilityService**:
- API 레벨 1+
- 권한: BIND_ACCESSIBILITY_SERVICE
- 장점: 앱 전환 이벤트 실시간 감지
- 제한: 배터리 소비 높음, 사용자 접근성 서비스로 인지
- 용도: 실시간 오버레이 트리거 신호

### 6.2 오버레이 (화면 위에 캐릭터 표시)

**SYSTEM_ALERT_WINDOW 권한**:
- 권한: `android.permission.SYSTEM_ALERT_WINDOW`
- 용도: 다른 앱 위에 자유로운 위치의 뷰 표시
- 구현: `WindowManager` + `OVERLAY_TYPE_APPLICATION_OVERLAY` (API 26+)
- 애니메이션: React Native Reanimated로 단계적 확대, 파티클 효과 구현

**오버레이 트리거 조건**:
1. 사용자가 제한 앱(틱톡, 인스타, 유튜브) 열기
2. UsageStatsManager + AccessibilityService로 진입 감지
3. 누적 사용 시간 ≥ goal_minutes 진입 시점
4. 오버레이 표시 신호를 백엔드에서 받거나 앱에서 로컬 판정
5. 오버레이 표시 → 단계 1(소), 단계 2(중), 단계 3(대) → 햅틱 피드백

### 6.3 이미지 처리 (ML Kit Subject Segmentation)

**구현 위치**: 온디바이스 (사용자 기기에서만 처리)
- 라이브러리: `com.google.mlkit:subject-segmentation`
- 프로세스:
  1. 카메라 또는 갤러리에서 반려동물 사진 선택
  2. ML Kit이 배경을 투명하게 제거
  3. 픽셀 아트 변환 (별도 알고리즘, 박현식 담당)
  4. pixel_image_url로 저장 (또는 Base64 인라인)

**외부 생성형 AI 비사용**:
- 클로드, GPT, 미드저니 등 외부 API 미사용
- 이유: 오프라인 작동 가능, 사용자 데이터 프라이버시 보호, API 비용 절감

### 6.4 배터리 및 성능

**배터리 최적화**:
- AccessibilityService는 필요할 때만 활성화 (부팅 후 또는 설정에서 명시적 활성화)
- UsageStatsManager는 주기적 폴링 (배터리 효율적)
- 오버레이는 사용자 인터랙션 없으면 자동 닫기 (TTL: 30초)

**메모리 요구사항**:
- ML Kit 모델 크기: ~10MB (다운로드 첫 실행 시)
- 반려동물 픽셀 이미지: 512x512 @ 100KB 추정

### 6.5 권한 요청 순서

1. **필수**: PACKAGE_USAGE_STATS, INTERNET, ACCESS_NETWORK_STATE
2. **권장**: BIND_ACCESSIBILITY_SERVICE (실시간 감지), SYSTEM_ALERT_WINDOW (오버레이)
3. **선택**: CAMERA (사진 촬영), READ_EXTERNAL_STORAGE (갤러리 접근)

---

## 7. 비기능 요구사항

### 7.1 성능

| 지표 | 목표 | 측정 방법 |
|------|------|---------|
| API 응답 시간 | ≤ 200ms (P95) | 로드 테스트 (k6, JMeter) |
| DB 쿼리 시간 | ≤ 50ms (인덱스 활용) | EXPLAIN ANALYZE |
| 앱 시작 시간 | ≤ 2초 | 프로파일링 (Perfetto) |
| 메모리 사용 | ≤ 300MB (RSS) | 메모리 모니터 |
| 오버레이 렌더링 FPS | ≥ 60 FPS | Android Profiler |

### 7.2 보안

| 요구사항 | 구현 |
|--------|------|
| **인증** | Supabase JWT (RS256), 토큰 유효기간 1시간 |
| **암호화** | HTTPS/TLS 1.3, in-transit 암호화 |
| **비밀번호** | bcrypt (Supabase 자동 처리), 최소 8자 |
| **입력 검증** | Pydantic BaseModel, 이메일/길이 검증 |
| **CORS** | 허용 출처 명시 (프론트엔드 도메인 또는 localhost) |
| **Rate Limiting** | 로그인 실패 5회 → 계정 잠금 (선택) |
| **민감 데이터** | 사진 URL은 서명된 URL 또는 Private CDN 제공 |
| **접근 제어** | 사용자는 자신의 데이터만 조회/수정 가능 (경로 매개변수 검증) |

### 7.3 가용성

| 지표 | 목표 | 비고 |
|------|------|------|
| SLA 가용성 | 99.5% | 월간 다운타임 ≤ 3.6시간 |
| RTO (복구 시간) | 30분 | 자동 페일오버 (별도 구성 필요) |
| RPO (데이터 손실) | 1시간 | Supabase 자동 백업 (일일 1회) |

### 7.4 확장성

- **수평 확장**: FastAPI는 stateless → 로드 밸런서 뒤에 여러 인스턴스 배포 가능
- **데이터베이스**: Supabase (관리형) → 자동 스케일링 (읽기 복제본 추가 가능)
- **세션 관리**: JWT 토큰 기반 → 세션 스토어 불필요

### 7.5 모니터링 및 로깅

| 항목 | 도구 | 빈도 |
|------|------|------|
| 서버 로그 | Python logging + 파일 쓰기 또는 CloudWatch | 실시간 |
| 성능 메트릭 | Prometheus + Grafana (선택) 또는 AWS CloudWatch | 1분 간격 |
| 에러 추적 | Sentry (선택) | 실시간 |
| 앱 크래시 | Firebase Crashlytics | 실시간 |

---

## 8. 배포 및 운영

### 8.1 개발 환경

```bash
# 백엔드 셋업
git clone <repo>
cd BE
python -m venv venv
source venv/bin/activate  # Linux/Mac
pip install -r requirements.txt
cp .env.example .env  # 환경 변수 설정
uvicorn app.main:app --reload
```

### 8.2 프로덕션 배포

**옵션 1: AWS (권장)**
- EC2 + ALB + RDS (Supabase 대체 가능)
- Docker: `docker build -t petox-api:latest .`
- Orchestration: ECS Fargate (서버리스) 또는 EKS (Kubernetes)

**옵션 2: Heroku**
- 소규모 팀에 적합
- `Procfile` 작성 후 `git push heroku main`
- 비용: 딕노 $7/월 (미니)

**옵션 3: Railway / Render**
- 자동 배포, 저비용 (~$5/월)

### 8.3 CI/CD 파이프라인

```yaml
# GitHub Actions 예시 (.github/workflows/deploy.yml)
name: Deploy
on:
  push:
    branches: [main]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Test API
        run: |
          pip install -r requirements.txt
          pytest tests/
  deploy:
    needs: test
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Deploy to Heroku
        run: git push heroku main
```

### 8.4 환경 변수 (.env)

```env
DATABASE_URL=postgresql://user:pass@host:5432/petox
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your-anon-key
SECRET_KEY=your-secret-for-jwt  # 선택
DEBUG=False
```

### 8.5 데이터베이스 마이그레이션

- **현재**: schema.sql 직접 실행 (Supabase 대시보드)
- **향후**: Alembic (SQLAlchemy 마이그레이션 도구) 도입 권장

```bash
alembic init migrations
alembic revision --autogenerate -m "Initial schema"
alembic upgrade head
```

---

## 9. 기술 위험 및 완화 전략

| 위험 | 영향도 | 완화 전략 |
|------|--------|---------|
| **안드로이드 권한 정책 변경** | 높음 | 최신 API 레벨 대응, OS 버전별 권한 처리 |
| **Supabase 의존성** | 중간 | 데이터 정기 백업, 마이그레이션 계획 보유 |
| **ML Kit 모델 업데이트** | 낮음 | 오프라인 대체 로직 (사용자 수동 확인) |
| **데이터베이스 성능 저하** | 중간 | 인덱스 최적화, 쿼리 모니터링, 읽기 복제본 추가 |
| **API 과부하** | 중간 | Rate limiting, 캐싱 (Redis 선택), 비동기 태스크 큐 (Celery) |

---

## 10. 향후 확장 사항 (우선순위)

| 우선순위 | 기능 | 대상 | 비고 |
|--------|------|------|------|
| P0 (필수) | 로그인/로그아웃 | 회원 관리 | 경진대회 최종 제출 전 필수 |
| P0 (필수) | 미션 조회 및 완료 | 코어 게임 루프 | 사용자 참여 직결 |
| P0 (필수) | 주간 리포트 | 데이터 분석 | 사용자 인사이트 제공 |
| P1 (권장) | 실시간 알림 | 참여도 향상 | WebSocket 또는 FCM 필요 |
| P1 (권장) | 리더보드 (친구 비교) | 경쟁 요소 | 사용자 공개 설정 필요 |
| P2 (선택) | AI 채팅봇 | 캐릭터 상호작용 | 별도 NLU 엔진 필요 |
| P2 (선택) | 소셜 공유 | 바이럴 마케팅 | SNS API 통합 |

---

## 11. 테스트 계획

### 11.1 유닛 테스트
- API 엔드포인트: pytest 사용
- 커버리지 목표: ≥ 80%

```bash
pytest tests/ --cov=app --cov-report=html
```

### 11.2 통합 테스트
- 데이터베이스 연동: TestClient + SQLite in-memory (또는 test DB)
- 이메일/SMS: Mock 사용

### 11.3 로드 테스트
- 도구: k6, Apache JMeter
- 목표: 100 동시 사용자, 평균 응답 시간 ≤ 200ms

### 11.4 안드로이드 기능 테스트
- UsageStatsManager: Emulator에서 런처 기본값 변경, adb 명령으로 시뮬레이션
- 오버레이: 물리 기기에서만 가능 (Emulator 미지원)

---

## 12. 검증 체크리스트

### 표준 TRD 항목 대조

- [x] **1. 개요**: 프로젝트 정의, 핵심 기능, 기대 효과 ✓
- [x] **2. 시스템 아키텍처**: 계층도, 데이터 흐름 ✓
- [x] **3. 기술 스택**: FE/BE/DB/안드로이드 명시 ✓
- [x] **4. API 명세**: 구현 완료 4개 + 향후 확장 20개 ✓
- [x] **5. 데이터베이스 스키마**: 11개 테이블 정의 ✓
- [x] **6. 안드로이드 특화 요구사항**: 권한, 감지, 오버레이, ML Kit ✓
- [x] **7. 비기능 요구사항**: 성능, 보안, 가용성, 확장성, 모니터링 ✓
- [x] **8. 배포 및 운영**: 개발 환경, 배포 옵션, CI/CD, 마이그레이션 ✓
- [x] **9. 위험 및 완화**: 5개 위험 항목 ✓
- [x] **10. 향후 확장**: 우선순위별 P0/P1/P2 ✓
- [x] **11. 테스트 계획**: 유닛/통합/로드/기능 테스트 ✓

### 프로젝트 실제 상태 반영 검증

- [x] DB 스키마: 실제 11개 테이블 모두 포함 ✓
- [x] 구현된 API: /health, /db-health, /items/{id}, /auth/signup 4개 명시 ✓
- [x] 기술 스택: React Native, FastAPI, PostgreSQL/Supabase 명시 ✓
- [x] 안드로이드 기능: UsageStatsManager, AccessibilityService, SYSTEM_ALERT_WINDOW, ML Kit 모두 명시 ✓
- [x] 팀 역할: PM/디자인(최수빈), BE(김민형), FE(박민규), AI(박현식) 포함 ✓
- [x] 일정: 최종 제출일 2026-10-01 명시 ✓

---

**문서 작성자**: 김민형 (Backend Lead)  
**최종 검토일**: 2026-09-04  
**다음 검토 예정**: 2026-09-18 (2주 후)
