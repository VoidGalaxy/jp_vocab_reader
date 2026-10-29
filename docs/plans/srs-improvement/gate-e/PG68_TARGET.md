# PG68 대상 값 (LQ1 접근 판정 잠금 실제 로컬 PG 검증, 2026-10-29 E1 확정)

이 문서는 등록한 대상 값을 적는다. 등록만으로 자원은 만들어지지 않는다. V2~V4는 계획 14절의 별도 승인으로 실행 `20261029T170041`에서 각 1회 수행됐고, 본 검사 24/24·정리·보관을 독립 검토했다(15절). 새 실제 실행과 운영 활성화는 별도 승인 대상이다.

| 항목 | 값 |
| --- | --- |
| 프리셋 | `PG68_LEXEME_ACCESS_LOCK`(`backend/tests/_ops_pg62.py`), 레이아웃 `PG68`(`backend/tests/_ops_real_layout.py`) |
| 폴더 | `C:/JV_Tools/pg68`(`data`·`tls`·`runs`) |
| 주소 | localhost:55522 |
| 관리자 역할 | `jpvk_admin`(부트스트랩, 업무 연결 아님) |
| 소유자 역할 | `jpvk_owner`(NOLOGIN) |
| 업무 역할 | `jpvk_read`, `jpvk_write` |
| 템플릿 DB | `jp_vocab_test_access_lock_tpl`(관리자·소유자만) |
| 검사 DB | `jp_vocab_test_access_lock_<ID>`, ID는 `k1` `k2a` `k2b` `k3` `s1` `s2` `s3` `s3b` `s4` `r1` `r2` `r3` `r4a` `r4b` `r5` `r6` `c1a` `c1b` `t1` `d1` `w1a` `w1b` `w2a` `w2b`(24개, 순서 고정) |
| 두 경로 DB | `r6` `c1a` `c1b` `w1b` `w2b`(준비 단계에서 계정 a의 덱 B 구독만 활성화, 나머지는 단일 경로) |
| 실행기 | `backend/tests/_ops_access_lock_real.py`(`prepare` / `check-access-lock` / `cleanup`, 다른 인자 없음) |
| 승인 상수 | `LQ4_CHANGES_APPROVED = True`(14절의 시험 대상 1회 승인 기록). `None`·`False`일 때 G0 전 차단은 가짜 보호 검사에서 명시적으로 확인한다 |

계획: `OPS_MIGRATION_ACCESS_LOCK_REAL_PG_PLAN.md`.
