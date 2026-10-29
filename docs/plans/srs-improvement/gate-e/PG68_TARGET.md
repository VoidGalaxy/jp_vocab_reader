# PG68 대상 값 (LQ1 접근 판정 잠금 실제 로컬 PG 검증, 2026-10-29 E1 확정)

이 문서는 등록한 대상 값만 적는다. 이 값을 등록해도 폴더·클러스터·역할·DB는 만들어지지 않는다. 준비(V2)·실제 검사(V3)·정리(V4)는 별도 승인 대상이며, 이번 V1에서는 승인되지 않았다.

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
| 승인 상수 | `LQ4_CHANGES_APPROVED = None`(V3 승인 전에는 `check-access-lock`이 G0 전에 종료 1) |

계획: `OPS_MIGRATION_ACCESS_LOCK_REAL_PG_PLAN.md`.
