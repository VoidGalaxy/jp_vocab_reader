# 클로드 작업 지시: SRS 교체 Gate A

`jp_vocab_reader`의 기존 고정 단계 SRS를 FSRS 기반으로 교체하려고 한다. 이번에는 **Gate A 계약 검토/실제 기준선 재현만** 진행하고 결과를 보고한 뒤 멈춰라. 엔진 설치, 제품 SRS 교체, 운영 자료 이전은 아직 시작하지 마라.

먼저 현재 체크아웃/HEAD/변경 파일과 루트 및 관련 경로의 AGENTS.md를 확인해라. 계획 기준은 main `e2c07f8`이지만 실제 상태가 바뀌었으면 새 기준을 보고해라. 기존 사용자 변경/미추적 파일은 보존하고 임의 삭제/덮어쓰기를 하지 마라. 브랜치 생성은 사용자가 요청한 경우만 진행하고, 생성 시 `codex/fsrs-srs-replacement`를 사용한다.

읽을 파일:

- `docs/plans/srs-improvement/REPLACEMENT_PLAN.md`
- `docs/plans/srs-improvement/IMPLEMENTATION_CONTRACT.md`
- `docs/plans/srs-improvement/PRODUCT_SRS_DESIGN.md`
- `docs/plans/srs-improvement/AUDIT_AND_RESEARCH.md`
- 현재 `docs/learning-plan.md`, `docs/operations/database-safety.md`

확정된 제품 용어는 **학습 완료**다. '기억 안정'을 기본 화면 용어로 사용하지 않는다. 완료는 주요 의미의 학습 목표 달성이며, 완료 뒤 유지 복습을 계속한다. FSRS 난이도/안정도/회상 확률 자체의 수식을 새로 작성하거나 분류에 따라 임의 가산하지 않는다.

이번 결과물:

1. 기존 audit_current_srs.py의 15개 현재 동작을 세션 전용 합성 SQLite에서 재확인한다. 실제 현재 동작과 새로운 권장 정책을 구분해 보고한다.
2. 실제 앱에서 평가 응답을 지연시켜 계정 전환/세션 교체/새 세션 시작, 응답 유실 재시도/중복 클릭을 확인한다. 정적 위험을 실제 재현이라고 쓰지 않는다. Gate A에서는 제품 수정 없이 결과를 기록한다.
3. `fsrs==6.3.2` 배포물 후보의 Python/API/라이선스/상태 직렬화/당일 전이/버전 범위를 공식 원본으로 검토한다. main README와 고정 배포물이 같다고 가정하지 않는다. 아직 설치하지 않는다.
4. 계약 결정표를 작성한다. 유지율 90%, 학습/재학습 10분 한 단계, 최대 365일, 완료 기준 S>=30일/서로 다른 날짜 성공2회/실제7일 간격 성공, 기존 known 동의 기반 재참여, 실제 신규 목표와 계정 전체 상한을 권장 초안으로 검토한다. 수치를 과학적으로 확정된 기준이라 쓰지 않는다.
5. 자유 복습을 SRS 비갱신 연습으로 둘지, 일일 상한을 별도 단계로 분리할지 또는 신규 claim의 TTL/자정 유예까지 구현할지 비교해라. 숫자/정책을 몰래 확정하지 말고 사용자 결정이 필요한 항목만 묶어 제시해라.
6. 완전/불완전 이력의 이전, 기존 due 보호, 동시 평가, 롤백 후 새 평가 보존을 합성 검산표로 정리하고 API/스키마 diff 초안을 만든다. 기존 로그/카드 ID/권한/분류는 보존하고, review_level을 S 일수로 환산하지 않는다.

산출물은 `docs/plans/srs-improvement/gate-a/REPORT.md`, `DECISIONS.md`와 필요한 작은 합성 검증 자료로 제한한다. 실제 원문/계정 비밀번호/토큰/DB URL/사용자 로그는 넣지 않는다. 제품 코드, package/requirements, 기존 저장 키, UI/에셋은 변경하지 않는다.

안전 규칙: 앱/DB import 전에 임시 SQLite DATABASE_URL을 지정한다. Neon/운영/기존 로컬 DB에는 접근하지 않는다. PG는 보호된 빈 로컬 테스트 DB에서만 허용되며 없으면 미검증으로 보고한다. 기존 서버는 건드리지 말고 자신이 시작한 서버/QA origin 키/임시 DB만 정리한다. 수정 파일/재현 결과/승인 필요 항목/미검증을 보고하고 Gate B 전에 멈춰라. 스테이징/커밋/푸시/병합은 하지 마라.
