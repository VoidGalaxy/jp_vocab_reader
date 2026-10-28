# 클로드 작업 지시: FSRS 교체 Gate B-1

프로젝트 `C:/JV_Project/jp_vocab_reader`에서 **Gate B-1만 구현/검증**하고 보고 후 멈춰라. 사용자 승인 기록은 `docs/plans/srs-improvement/APPROVAL_2026-10-09.md`다. Gate B-2 이후 자동 진행은 승인되지 않았다.

## 시작 전

적용되는 AGENTS.md, 현재 브랜치/HEAD/dirty 상태를 확인해라. 기존 `docs/roadmap.md` 변경, 이미지/목업/QA/tsbuildinfo 등 사용자 자료는 보존한다.
승인된 작업 브랜치 `codex/fsrs-srs-replacement`를 만들거나 같은 작업의 기존 브랜치를 재사용한다. 이미 관계없는 작업 브랜치에 있다면 임의 전환/삭제하지 말고 보고한다. main에서 제품 구현하지 않는다.

아래 문서를 실제 코드와 대조한다. 승인 이전 문구와 충돌하면 승인 기록이 우선이다.

- `docs/plans/srs-improvement/APPROVAL_2026-10-09.md`
- `docs/plans/srs-improvement/gate-a/DECISIONS.md`, `REPORT.md`
- `docs/plans/srs-improvement/REPLACEMENT_PLAN.md`
- `docs/plans/srs-improvement/IMPLEMENTATION_CONTRACT.md`
- `docs/plans/srs-improvement/PRODUCT_SRS_DESIGN.md`
- `docs/operations/database-safety.md`

## 구현할 것

1. `backend/requirements.txt`에 `fsrs==6.3.2`를 정확히 고정하고 로컬 venv에 설치한다. 배포물 해시/실제 설치 버전/라이선스/로컬 Python 호환성을 기록한다. optimizer는 설치하지 않는다. 운영 Python은 확인할 수 있는 설정만 조사하고 미확인이면 그대로 보고한다. 운영 서비스/환경을 임의 변경하지 않는다.
2. UTC 시각/카드 ID를 명시적으로 받는 순수 엔진 어댑터를 구현한다. 기본 파라미터, 유지율0.90, 학습(1분,10분), 재학습10분, 최대365일, fuzz끔을 사용한다. 수식을 손으로 구현하거나 간격/안정도를 임의 보정하지 않는다. 설정/라이브러리/어댑터 버전과 직렬화를 재현 가능하게 유지한다.
3. 기존 개인/구독 카드와 두 로그 테이블을 유지하고 필요한 SRS 필드, 계정 설정, 평가 영수증, 이전 run/snapshot 저장 구조를 추가형으로 만든다. 기존 DB 추상화/패턴을 우선한다. 신규 예약 테이블은 만들지 않는다. 필드·제약·인덱스 선택과 실제 변경 파일을 보고한다.
4. SQLite/PG 스키마의 새 DB 생성과 기존 합성 DB 업그레이드·재실행을 확인한다. legacy 기본값을 유지하고 기존 단어/분류/레벨/예약/로그를 변경하지 않는다. startup에 이력 재생·known 자동 이전·FSRS 활성화를 넣지 않는다.
5. 학습 완료 판정 함수를 테스트용 기준으로 구현한다. Review, S>=30일, 마지막 Again 이후 서울 날짜2개 성공, 그중 직전 유효 평가와 실제7일 이상 간격 성공이다. 첫 Easy/같은 날 반복을 완료로 세지 않는다. 불완전 증거는 미확인과 실패를 구분하고, 실패/보류/재개/최초 완료 이력 보존을 검증한다.
6. 네 평가·각 상태 전이, 같은 날/다른 날/장기 연체, 최대 간격, UTC/서울 날짜 경계, 잘못된 상태/시각, 직렬화 round-trip, 설정 버전 재현을 실제 라이브러리로 테스트한다. 개인/구독 ID는 엔진 내부 ID만 같다고 자료를 합치지 않는다.
7. 합성 시나리오로 계속 Good/Easy, 중간 Again, 반복 Hard, 당일 반복을 비교한다. 실제 다음 예약 시각과 완료 조건 도달 평가 수/경과일을 기록하고, 미도달/관측 종료도 구분한다. 합성 결과를 학습 효과 증명으로 보고하지 않는다. 완료 기준은 결과를 보고 사용자 재승인을 받는다.

## 범위 밖

평가 API 전환/중복 영수증 실행 배선/카드 CAS 실행/이력 이전 도구 실행은 Gate B-2다. 실제 동적 큐/신규 목표 집행/자유 복습 변경/화면 수정은 이후 단계다.
`page.tsx`, 학습 계획/통계 화면, 읽기 저장v3, 기존 평가/출제 경로는 바꾸지 않는다. 기존 테스트의 기대값을 FSRS에 맞춰 조용히 바꾸지 않고 legacy 회귀를 유지한다.
서울 화면 실적 통일은 Gate D다. 이번에는 기존 `/stats` 집계를 바꾸지 않는다.

## 검증과 안전

DB/app import 전에 session-only SQLite DATABASE_URL과 로컬 APP_ENV를 지정한다. Neon/운영/기존 로컬 DB에는 접근하지 않는다. PG 테스트는 기존 보호 검사를 통과한 빈 로컬 테스트 DB만 쓰고, 대상 환경변수가 실행 중 바뀌면 쓰기 전에 중단한다. PG가 없으면 설치/원격 우회 없이 미검증으로 보고한다.

새 백엔드 테스트, 기존 SRS/학습 계획/구독 회귀, 프론트 npm test와 typecheck, diff check를 실행한다. 프론트를 수정하지 않았다면 이 게이트에서는 불필요한 build를 반복하지 않는다.
합성 DB의 기존 행/로그/예약/분류와 legacy 평가 결과가 동일함을 확인한다. DDL 테스트 통과를 FSRS 평가/운영 이전 통과로 보고하지 않는다.
기존 서버/파일은 건드리지 말고 자신이 만든 임시 DB/스크래치/QA 서버만 정리한다.

산출물은 `docs/plans/srs-improvement/gate-b1/REPORT.md`와 작은 시뮬레이션 결과/재현용 검사다. 실제 사용자 자료·토큰·비밀번호·DB URL·DB 파일을 문서/커밋 후보에 넣지 않는다.
보고에는 변경 파일, 엔진 실제 결과, 데이터 보존, 테스트 결과, 완료 기준 재승인 항목, 미검증/다음 단계 위험을 포함한다.
**스테이징·커밋·푸시·병합 없이 Gate B-1 종료 지점에서 멈춰라.**
