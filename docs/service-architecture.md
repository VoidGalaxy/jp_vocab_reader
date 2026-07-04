# 서비스형 구조 전환 설계

이 문서는 현재 로컬 SQLite 기반 `jp-vocab-reader`를 여러 사용자가 함께 쓰는 웹서비스로 확장하기 위한 설계 초안이다. 현재는 백엔드 회원가입/로그인 API와 JWT access token을 지원하며, 토큰이 없으면 개발용 기본 사용자로 fallback한다.

## A. 현재 구조 요약

- 현재 앱은 SQLite 기반 로컬 앱 구조다.
- 주요 영속 데이터는 `decks`, `vocab_items`, `custom_terms` 중심으로 관리된다.
- 분석 카드 분류 진행상태는 브라우저 `localStorage` draft로 임시 저장된다.
- 현재 API는 `Authorization: Bearer <token>`이 있으면 토큰 사용자를 현재 사용자로 사용하고, 토큰이 없으면 개발용 기본 사용자 `dev@example.local`을 사용한다.
- 잘못되었거나 만료된 토큰은 백엔드에서 `401 Unauthorized`로 거부하고, 프론트엔드는 저장된 토큰을 제거한 뒤 개발용 기본 사용자 흐름으로 복구한다.
- `decks`, `vocab_items`, `custom_terms`에는 `user_id` 컬럼이 있으며 기존 데이터는 개발용 기본 사용자 소유로 마이그레이션한다.
- 덱, 단어장, 사용자 정의 용어, 학습 기록은 repository 계층에서 현재 사용자 `user_id` 조건으로 조회/수정/삭제한다.
- 단어 생성/수정, 분석, 통계, 학습, CSV/JSON export처럼 `deck_id`를 받는 개인 데이터 요청은 현재 사용자 소유 덱인지 먼저 확인한다.
- DB 연결 설정은 `DATABASE_URL` 환경변수를 읽는다. 값이 없으면 기존 `backend/vocab.db` SQLite 파일을 사용하고, `sqlite:///...` URL이면 해당 SQLite 파일을 사용한다.
- `postgresql://...` URL은 아직 런타임 지원 대상이 아니며, 이후 마이그레이션 단계에서 지원할 예정이다.
- 현재 덱 공유 JSON export/import는 로컬 파일을 통해 덱을 복사하는 방식이다.

## B. 서비스형 전환 목표

- `users` 테이블을 추가해 계정 단위 소유권을 만든다.
- auth foundation 단계에서 `users` 테이블과 개발용 기본 사용자 생성을 완료했다.
- user-scoped-data 단계에서 사용자별 개인 덱, `vocab_items`, `custom_terms`, 학습 기록 조회/수정 범위 분리를 완료했다.
- auth-api 단계에서 회원가입/로그인 API, 비밀번호 해시 저장, JWT access token 발급, 토큰 사용자 처리, dev user fallback을 완료했다.
- 공유 덱 패키지와 공개 덱 마켓 구조를 분리한다.
- 추후 서비스 배포 전 PostgreSQL 전환을 권장한다.
- Anki처럼 사용자가 자신의 덱을 공유하고, 다른 사용자가 공개 덱을 가져와 개인 덱으로 복사할 수 있게 한다.

## C. 권장 DB 테이블 초안

### users

서비스 계정의 기준 테이블이다.

- `id`: 사용자 고유 ID.
- `email`: 로그인 이메일. 고유해야 한다.
- `password_hash`: 비밀번호 해시. 소셜 로그인만 사용할 경우 nullable 가능.
- `display_name`: 화면 표시 이름.
- `role`: 일반 사용자, 관리자 등 권한 구분.
- `created_at`: 가입 시각.
- `updated_at`: 마지막 수정 시각.
- `last_login_at`: 마지막 로그인 시각.
- `is_active`: 계정 활성 여부.

### decks

사용자 개인 덱 테이블이다.

- `id`: 개인 덱 고유 ID.
- `user_id`: 덱 소유자. `users.id`를 참조한다.
- `name`: 덱 이름.
- `description`: 덱 설명.
- `source_shared_deck_id`: 공유 덱에서 가져온 경우 원본 `shared_decks.id`.
- `source_package_version`: 가져온 공유 패키지 버전.
- `is_default`: 기본 단어장 여부.
- `created_at`: 생성 시각.
- `updated_at`: 수정 시각.

권장 제약:

- 같은 사용자 안에서 `name` 중복 정책을 정한다.
- 기본 덱은 사용자별 하나만 허용한다.
- 모든 개인 단어와 학습 기록은 이 테이블을 기준으로 사용자 소유권을 확인한다.

### vocab_items

사용자 개인 단어장 항목과 학습 기록을 함께 보관하는 테이블이다. 서비스 규모가 커지면 학습 기록을 별도 `study_records` 또는 `vocab_review_states` 테이블로 분리할 수 있다.

- `id`: 단어 항목 고유 ID.
- `user_id`: 항목 소유자. `users.id`를 참조한다.
- `deck_id`: 소속 개인 덱. `decks.id`를 참조한다.
- `surface`: 표면형.
- `lemma`: 기본형.
- `reading`: 읽기.
- `part_of_speech`: 품사.
- `meaning_ko`: 한국어 뜻.
- `dictionary_gloss`: JMdict 등 사전 gloss 참고값.
- `example_sentence`: 짧은 예문.
- `quality_tag`: 일반 토큰, 사용자 용어, 복합동사, 명사구 후보 등 분석 후보 유형.
- `status`: `known`, `uncertain`, `unknown`, `unclassified` 같은 학습 상태.
- `correct_count`: 맞은 횟수.
- `wrong_count`: 틀린 횟수.
- `review_level`: 복습 단계.
- `next_review_at`: 다음 복습 예정 시각.
- `last_reviewed_at`: 마지막 복습 시각.
- `context_explanation_ko`: AI 문맥 설명.
- `created_at`: 생성 시각.
- `updated_at`: 수정 시각.

권장 제약:

- 모든 조회/수정/삭제 쿼리에 `user_id` 조건이 필요하다.
- `deck_id`의 소유자와 `vocab_items.user_id`는 항상 같아야 한다.

### custom_terms

사용자 정의 용어 사전 테이블이다.

- `id`: 사용자 정의 용어 고유 ID.
- `user_id`: 용어 소유자. `users.id`를 참조한다.
- `deck_id`: 특정 덱 전용 용어일 경우 `decks.id`. 공통 용어는 nullable.
- `term`: 용어 표기.
- `reading`: 읽기.
- `part_of_speech`: 품사.
- `meaning_ko`: 한국어 뜻.
- `description`: 설명.
- `created_at`: 생성 시각.
- `updated_at`: 수정 시각.

권장 제약:

- 같은 사용자 안에서 `term`과 `deck_id` 조합의 중복을 제한한다.
- 특정 덱 용어는 해당 덱 소유자만 수정할 수 있다.

### shared_decks

공개 또는 링크 공유 가능한 덱 패키지의 메타데이터 테이블이다.

- `id`: 공유 덱 고유 ID.
- `owner_user_id`: 공유 덱 작성자. `users.id`를 참조한다.
- `title`: 공개 덱 제목.
- `description`: 공개 설명.
- `language`: 대상 언어. 기본값은 `ja`.
- `visibility`: `public`, `unlisted`, `private` 등 공개 범위.
- `version`: 공유 패키지 버전.
- `item_count`: 공유 단어 수.
- `term_count`: 공유 사용자 정의 용어 수.
- `download_count`: 가져오기 또는 다운로드 수.
- `source_label`: 작품명, 장르, 원본 출처 등 사용자가 입력한 설명.
- `license_note`: 공유자가 명시한 라이선스/주의 문구.
- `created_at`: 생성 시각.
- `updated_at`: 수정 시각.
- `published_at`: 공개 시각.

권장 정책:

- 공유 덱에는 개인 학습 기록을 포함하지 않는다.
- 공개 읽기는 허용하되 수정은 작성자와 관리자만 허용한다.

### shared_deck_items

공유 덱에 포함된 단어 항목 테이블이다.

- `id`: 공유 단어 고유 ID.
- `shared_deck_id`: 소속 공유 덱. `shared_decks.id`를 참조한다.
- `surface`: 표면형.
- `lemma`: 기본형.
- `reading`: 읽기.
- `part_of_speech`: 품사.
- `meaning_ko`: 한국어 뜻.
- `dictionary_gloss`: 사전 gloss 참고값.
- `example_sentence`: 짧은 예문.
- `quality_tag`: 분석 후보 유형.
- `sort_order`: 공유 덱 안의 표시 순서.
- `created_at`: 생성 시각.

제외해야 하는 값:

- `status`
- `correct_count`
- `wrong_count`
- `review_level`
- `next_review_at`
- `last_reviewed_at`
- 개인 덱의 내부 `id`, `deck_id`, `user_id`

### shared_deck_terms

공유 덱에 포함된 사용자 정의 용어 테이블이다.

- `id`: 공유 용어 고유 ID.
- `shared_deck_id`: 소속 공유 덱. `shared_decks.id`를 참조한다.
- `term`: 용어 표기.
- `reading`: 읽기.
- `part_of_speech`: 품사.
- `meaning_ko`: 한국어 뜻.
- `description`: 설명.
- `sort_order`: 공유 덱 안의 표시 순서.
- `created_at`: 생성 시각.

### deck_imports

공유 덱을 개인 덱으로 가져온 이력을 기록하는 테이블이다.

- `id`: 가져오기 이력 고유 ID.
- `user_id`: 가져온 사용자. `users.id`를 참조한다.
- `shared_deck_id`: 원본 공유 덱. `shared_decks.id`를 참조한다.
- `created_deck_id`: 생성된 개인 덱. `decks.id`를 참조한다.
- `shared_deck_version`: 가져온 시점의 공유 덱 버전.
- `imported_item_count`: 복사된 단어 수.
- `imported_term_count`: 복사된 사용자 정의 용어 수.
- `created_at`: 가져오기 시각.

활용:

- 같은 공유 덱을 이미 가져왔는지 표시할 수 있다.
- 추후 업데이트 동기화 또는 새 버전 알림의 기반이 된다.

### ai_usage_logs 또는 usage_logs

AI 문맥 설명, 분석 요청, 공개 마켓 사용량 등을 추적하는 운영 로그 테이블이다.

- `id`: 로그 고유 ID.
- `user_id`: 요청 사용자. 비로그인 요청을 허용한다면 nullable 가능.
- `event_type`: `ai_context_explanation`, `analyze`, `deck_import`, `deck_publish` 등 이벤트 유형.
- `target_type`: `vocab_item`, `deck`, `shared_deck` 등 대상 유형.
- `target_id`: 대상 ID.
- `model`: AI 요청에 사용한 모델명.
- `input_tokens`: 입력 토큰 수.
- `output_tokens`: 출력 토큰 수.
- `cost_estimate`: 추정 비용.
- `status`: 성공, 실패, 제한됨 등 처리 상태.
- `error_code`: 실패 코드.
- `created_at`: 요청 시각.

활용:

- 사용자별 AI 사용량 제한.
- 비용 추적.
- 장애 분석.
- 과금 정책 또는 무료 사용량 정책의 기반.

## D. 개인 데이터와 공유 데이터 분리 정책

- 개인 덱은 사용자의 학습 기록을 포함한다.
- 개인 `vocab_items`에는 `status`, 맞음/틀림 횟수, 복습 레벨, 다음 복습일, AI 문맥 설명 같은 개인 상태가 포함된다.
- 공유 덱은 학습 기록을 제외한다.
- 공유 덱은 단어, 뜻, 읽기, 품사, 예문, 사용자 정의 용어처럼 다른 사용자에게 복사해도 되는 학습 자료만 포함한다.
- 공유 덱을 가져오면 원본 공유 데이터를 사용자의 개인 `decks`, `vocab_items`, `custom_terms`로 복사한다.
- 가져온 사람의 학습 기록은 항상 초기화한다.
- 가져온 단어의 기본 상태는 `unknown` 또는 서비스 정책상 정한 초기 상태로 둔다.
- 공유 덱 수정은 원본 공유 덱에만 반영되며, 이미 가져간 개인 덱에는 자동 반영하지 않는 것을 기본 정책으로 둔다.

## E. 현재 로컬 덱 패키지 기능과 미래 공유 마켓의 관계

- 현재 JSON export/import는 공유 마켓의 기반이다.
- 현재 `jp_vocab_reader_deck` JSON 패키지는 개인 학습 기록을 제외하고 덱 메타데이터, 단어, 덱 전용 사용자 정의 용어를 포함한다.
- 미래 공개 마켓에서는 같은 패키지 구조를 서버 DB의 `shared_decks`, `shared_deck_items`, `shared_deck_terms`에 저장하는 방식으로 확장할 수 있다.
- 사용자는 개인 덱을 `POST /decks/{id}/publish` 같은 API로 공유 덱에 업로드한다.
- 다른 사용자는 `shared_decks` 목록에서 덱을 찾고, `POST /shared-decks/{id}/import`로 자신의 개인 덱에 복사한다.
- JSON 파일 import는 계속 유지하면 오프라인 공유, 백업, 수동 이동 기능으로 쓸 수 있다.
- 서버 공유 마켓과 JSON 패키지의 필드 구조를 최대한 맞추면 export/import와 publish/import 로직을 재사용하기 쉽다.

## F. API 전환 계획

현재 API는 단일 사용자 기준이다. 인증 도입 후에는 대부분의 개인 데이터 API가 로그인 사용자 기준으로 동작해야 한다.

### 개인 데이터 API

- `GET /vocab-items`: 로그인 사용자의 단어만 반환한다.
- `POST /vocab-items`: 로그인 사용자의 단어로 생성한다.
- `PATCH /vocab-items/{id}`: 로그인 사용자가 소유한 단어만 수정한다.
- `DELETE /vocab-items/{id}`: 로그인 사용자가 소유한 단어만 삭제한다.
- `GET /vocab-items/export.csv`: 로그인 사용자의 전체 또는 특정 덱 단어만 CSV로 내보낸다.
- `GET /decks`: 로그인 사용자의 덱만 반환한다.
- `POST /decks`: 로그인 사용자의 개인 덱을 생성한다.
- `PATCH /decks/{id}`: 로그인 사용자가 소유한 덱만 수정한다.
- `DELETE /decks/{id}`: 로그인 사용자가 소유한 덱만 삭제한다.
- `GET /custom-terms`: 로그인 사용자의 공통/덱 전용 용어만 반환한다.
- `POST /custom-terms`: 로그인 사용자의 용어로 생성한다.
- `POST /decks/import-package`: 업로드한 JSON 패키지를 로그인 사용자의 개인 덱으로 복사한다.

### 공유 덱 API

- `GET /shared-decks`: 공개 공유 덱 목록을 반환한다.
- `GET /shared-decks/{id}`: 공개 또는 접근 가능한 공유 덱 상세를 반환한다.
- `POST /shared-decks/{id}/import`: 공유 덱을 로그인 사용자의 개인 덱으로 복사한다.
- `POST /decks/{id}/publish`: 로그인 사용자가 소유한 개인 덱을 공유 덱으로 게시한다.
- `PATCH /shared-decks/{id}`: 작성자 또는 관리자만 공유 덱 메타데이터를 수정한다.
- `DELETE /shared-decks/{id}`: 작성자 또는 관리자만 공유 덱을 비공개 처리하거나 삭제한다.

### 분석/AI API

- `POST /analyze`: 로그인 사용자의 사용자 정의 용어와 덱 컨텍스트를 기준으로 분석한다.
- `POST /vocab-items/{id}/context-explanation`: 로그인 사용자가 소유한 단어에 대해서만 AI 문맥 설명을 생성한다.
- AI 요청은 `ai_usage_logs` 또는 `usage_logs`에 기록한다.

## G. 인증/권한 계획

- auth foundation 단계는 완료했다. SQLite에 `users` 테이블을 만들고, 앱 시작 시 `dev@example.local` 개발 사용자를 자동 생성한다.
- auth-api 단계는 완료했다. `POST /auth/register`, `POST /auth/login`은 JWT access token을 반환한다.
- `GET /me`는 토큰이 있으면 토큰 사용자를 반환하고, 토큰이 없으면 개발용 기본 사용자를 반환한다.
- 비밀번호는 평문 저장하지 않고 `password_hash`에 해시로 저장한다.
- JWT secret은 `JWT_SECRET_KEY` 환경변수로 설정할 수 있으며, 개발 기본값은 로컬 용도다.
- 아직 프론트엔드 로그인/회원가입 UI와 refresh token/session 정책은 구현하지 않았다.
- `decks`, `vocab_items`, `custom_terms`에 `user_id`를 추가했고, 기존 데이터는 개발용 기본 사용자 소유로 마이그레이션한다.
- 모든 주요 repository 함수는 현재 사용자 `user_id`를 받아 해당 사용자 데이터만 조회/수정/삭제한다.
- 회원가입/로그인 기능을 도입한다.
- 현재 백엔드는 JWT access token을 사용한다.
- JWT 방식은 stateless API와 배포가 단순하지만 토큰 폐기, refresh token, XSS 대응 정책이 필요하다.
- 세션 방식은 서버 측 폐기가 쉽고 브라우저 앱과 잘 맞지만 세션 저장소와 CSRF 대응이 필요하다.
- 초기 서비스는 FastAPI 백엔드와 Next.js 프론트 구성을 고려해 쿠키 기반 세션 또는 httpOnly refresh token 구조를 우선 검토한다.
- 사용자는 자기 `deck`, `vocab_items`, `custom_terms`, 학습 기록만 조회/수정/삭제할 수 있다.
- `shared_decks`는 공개 읽기를 허용할 수 있다.
- 비공개 또는 링크 공유 덱은 `visibility` 정책에 따라 접근을 제한한다.
- 공유 덱 수정, 삭제, 새 버전 게시 권한은 작성자와 관리자에게만 부여한다.
- 관리자 권한은 신고 처리, 저작권 문제 대응, 공개 덱 비공개 처리에 필요하다.

## H. SQLite → PostgreSQL 전환 계획

- 개발 중에는 SQLite를 유지할 수 있다.
- postgres-readiness 단계에서 `DATABASE_URL` 기반 SQLite 설정, SQLite connection timeout, `row_factory`, `PRAGMA foreign_keys = ON`, 명시적 schema 초기화 함수 구조를 정리했다.
- 자세한 전환 계획은 [postgres-migration-plan.md](postgres-migration-plan.md)를 참고한다.
- 여러 사용자가 쓰는 서비스 배포 전에는 PostgreSQL 전환을 권장한다.
- PostgreSQL은 동시성, 인덱스, 트랜잭션, 백업, 운영 도구 측면에서 서비스 운영에 적합하다.
- SQLAlchemy 도입 여부를 검토한다.
- SQLAlchemy를 도입하면 SQLite와 PostgreSQL 사이의 DB adapter 전환, 테스트 DB 구성, 쿼리 재사용이 쉬워진다.
- 마이그레이션 도구로 Alembic을 검토한다.
- Alembic을 쓰면 `users`, `user_id`, 공유 덱 테이블 추가 같은 스키마 변경을 버전 관리할 수 있다.
- 기존 코드가 raw sqlite 쿼리 중심이라면 전환 난이도는 중간 이상이다.
- raw sqlite 코드가 넓게 퍼져 있다면 모든 쿼리에 `user_id` 조건을 추가해야 하고, placeholder 문법, 트랜잭션 처리, row 변환 방식도 정리해야 한다.
- DB 접근 계층 1차 정리는 완료했다. `backend/app/repositories` 아래에 덱, 단어장, 사용자 정의 용어, 통계, 덱 패키지 repository를 두고 endpoint는 요청 검증과 repository 호출 중심으로 유지한다.
- 현재 repository는 기존 SQLite 연결과 raw SQL을 그대로 사용한다.
- 이번 단계에서는 SQLAlchemy, PostgreSQL을 도입하지 않았다.
- `user_id` 필터링과 소유권 검사는 repository 계층에 적용했다.

## I. 단계별 구현 로드맵

1. 서비스 아키텍처 문서화
2. 사용자 모델 추가 준비
3. DB 접근 계층 정리 완료
4. PostgreSQL/SQLAlchemy 전환 또는 최소한 DB adapter 분리
5. auth foundation 완료
6. `user_id` 기반 데이터 분리 완료
7. auth-api 완료
8. 프론트엔드 로그인/회원가입 UI
9. `shared_decks` 공개 마켓
10. 배포
11. 사용량 제한/AI 과금 정책

## J. 리스크

- 기존 DB 마이그레이션 위험이 있다.
- `user_id` 도입 시 모든 개인 데이터 쿼리를 수정해야 한다.
- 일부 쿼리에 `user_id` 조건이 빠지면 사용자 간 데이터 노출 사고가 날 수 있다.
- 공유 덱과 개인 학습 기록을 혼동하면 다른 사용자의 학습 상태가 공유되거나 초기화 정책이 깨질 수 있다.
- AI 문맥 설명은 비용 관리가 필요하다.
- AI 사용량 제한, 실패 처리, 재시도 정책이 없으면 운영 비용이 예측하기 어렵다.
- 저작권/원문 저장 정책을 명확히 유지해야 한다.
- 원문 전체 저장을 피하고, 공유 덱에는 저작권 문제가 될 수 있는 긴 원문 발췌를 제한해야 한다.
- 공개 덱 마켓에는 신고, 비공개 처리, 라이선스 안내, 운영자 관리 기능이 필요할 수 있다.

## Shared Deck Market Foundation 완료

이번 단계에서 개인 덱과 공개 공유 덱을 분리하는 서버 내부 마켓 기반을 추가했다.

- 앱 시작 시 `shared_decks`, `shared_deck_items`, `shared_deck_terms`, `shared_deck_imports` 테이블을 생성한다.
- `POST /decks/{deck_id}/publish`는 현재 사용자의 개인 덱을 공개 공유 덱으로 복사한다.
- 공유 덱에는 단어, 뜻, 읽기, 품사, 예문, AI 문맥 설명, 품질 태그, 해당 덱 전용 사용자 정의 용어를 포함한다.
- 공유 덱에는 개인 학습 기록과 원문 전체를 포함하지 않는다.
- `GET /shared-decks`와 `GET /shared-decks/{shared_deck_id}`는 공개 공유 덱 목록과 상세를 제공한다.
- `POST /shared-decks/{shared_deck_id}/import`는 공유 덱을 현재 사용자의 개인 덱으로 복사하고 학습 상태를 초기화한다.
- 가져온 단어는 `status = unknown`, 정답/오답 횟수와 복습 단계 `0`, 다음 복습일 `NULL`로 시작한다.
- 프론트엔드는 공유 덱 가져오기 성공 후 생성된 개인 덱을 즉시 선택하고 단어장/사용자 정의 용어 목록을 다시 불러온다.
- 기존 JSON deck package export/import는 유지하며, 서버 공유 마켓은 같은 정책을 DB 테이블 기반으로 확장한 형태다.

TODO:

- 공유 덱 검색
- 좋아요/평점
- 신고/검수
- 페이지네이션
- 같은 덱 재등록 시 버전 업데이트 정책
- 저작권/원문 저장 제한 정책
