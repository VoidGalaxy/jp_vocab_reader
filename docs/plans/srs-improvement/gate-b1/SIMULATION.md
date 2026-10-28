# Gate B-1 합성 시뮬레이션: 학습 완료 초안 도달 시점

엔진: fsrs 6.3.2 실제 실행, 설정 `fsrs-6.3.2-a1-362bc5407f76` (기본 파라미터, 유지율 0.90, 학습 1분·10분, 재학습 10분, 최대 365일, fuzz 끔).
완료 초안: Review + S>=30일 + 마지막 다시 이후 서울 날짜 2개 성공 + 직전 평가와 7일 이상 간격 성공 1회.
시작 2026-10-12T01:00:00+00:00 (10:00 KST). 관측 한도: 평가 40회 또는 730일.
평가 패턴은 가상이다. 결과는 스케줄러와 완료 규칙의 동작이며 학습 효과가 아니다.

## 요약

| 시나리오 | 패턴 | 결과 | 평가 수 | 첫 평가부터 경과 | 그때 S(일) | 마지막 다음 간격 |
| --- | --- | --- | --- | --- | --- | --- |
| good_always | 매번 due 시각에 보통 | 도달 (4번째) | 4 | 13.0일 | 46.3 | 46일 |
| easy_always | 매번 due 시각에 쉬움 | 도달 (2번째) | 2 | 8.0일 | 65.6 | 66일 |
| hard_always | 첫 평가부터 매번 due 시각에 어려움 | 미도달 (관측 종료) | 40 | 0.1일 | 1.3 | 6분 |
| hard_after_review | 보통 2회로 Review 진입 후 매번 어려움 | 도달 (5번째) | 5 | 29.0일 | 35.8 | 36일 |
| again_first_then_good | 첫 평가 다시, 이후 보통 | 도달 (7번째) | 7 | 29.0일 | 48.3 | 48일 |
| good_with_mid_again | 보통, 4번째 평가만 다시, 이후 보통 | 도달 (9번째) | 9 | 60.0일 | 59.7 | 60일 |
| again_after_completion | 보통으로 완료(4번째) 직후 5번째 다시, 이후 보통으로 재완료까지 | 도달 (4번째), 실패 후 재도달 | 9 | 89.0일 | 41.7 | 42일 |
| hard_good_alternate | 어려움·보통 번갈아 | 도달 (9번째) | 9 | 46.0일 | 33.9 | 34일 |
| good_late_3d | 보통, 매번 due보다 3일 늦게 | 도달 (3번째) | 3 | 20.0일 | 63.2 | 63일 |
| same_day_repeat | 같은 날 10분마다 보통 20회 (그 뒤 관측 종료) | 미도달 (관측 종료) | 20 | 0.1일 | 2.3 | 2일 |

### good_always: 매번 due 시각에 보통

| # | 평가 시각(UTC) | 평가 | 단계 | S(일) | D | 다음 간격 | 완료 판정 | 미충족 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 2026-10-12 01:00 | good | learning/1 | 2.31 | 2.12 | 10분 | not_completed | not_review_phase, stability_below_threshold, fewer_success_dates, no_spaced_success |
| 2 | 2026-10-12 01:10 | good | review | 2.31 | 2.11 | 2일 | not_completed | stability_below_threshold, fewer_success_dates, no_spaced_success |
| 3 | 2026-10-14 01:10 | good | review | 10.97 | 2.10 | 11일 | not_completed | stability_below_threshold, no_spaced_success |
| 4 | 2026-10-25 01:10 | good | review | 46.32 | 2.10 | 46일 | completed | - |

### easy_always: 매번 due 시각에 쉬움

| # | 평가 시각(UTC) | 평가 | 단계 | S(일) | D | 다음 간격 | 완료 판정 | 미충족 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 2026-10-12 01:00 | easy | review | 8.30 | 1.00 | 8일 | not_completed | stability_below_threshold, fewer_success_dates, no_spaced_success |
| 2 | 2026-10-20 01:00 | easy | review | 65.62 | 1.00 | 66일 | completed | - |

### hard_always: 첫 평가부터 매번 due 시각에 어려움

| # | 평가 시각(UTC) | 평가 | 단계 | S(일) | D | 다음 간격 | 완료 판정 | 미충족 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 2026-10-12 01:00 | hard | learning/0 | 1.29 | 5.11 | 6분 | not_completed | not_review_phase, stability_below_threshold, fewer_success_dates, no_spaced_success |
| 2 | 2026-10-12 01:05 | hard | learning/0 | 1.29 | 6.74 | 6분 | not_completed | not_review_phase, stability_below_threshold, fewer_success_dates, no_spaced_success |
| 3 | 2026-10-12 01:11 | hard | learning/0 | 1.29 | 7.82 | 6분 | not_completed | not_review_phase, stability_below_threshold, fewer_success_dates, no_spaced_success |
| 4 | 2026-10-12 01:16 | hard | learning/0 | 1.29 | 8.54 | 6분 | not_completed | not_review_phase, stability_below_threshold, fewer_success_dates, no_spaced_success |
| 5 | 2026-10-12 01:22 | hard | learning/0 | 1.29 | 9.02 | 6분 | not_completed | not_review_phase, stability_below_threshold, fewer_success_dates, no_spaced_success |
| 6 | 2026-10-12 01:27 | hard | learning/0 | 1.29 | 9.33 | 6분 | not_completed | not_review_phase, stability_below_threshold, fewer_success_dates, no_spaced_success |
| 7 | 2026-10-12 01:33 | hard | learning/0 | 1.29 | 9.54 | 6분 | not_completed | not_review_phase, stability_below_threshold, fewer_success_dates, no_spaced_success |
| 8 | 2026-10-12 01:38 | hard | learning/0 | 1.29 | 9.68 | 6분 | not_completed | not_review_phase, stability_below_threshold, fewer_success_dates, no_spaced_success |
| 9 | 2026-10-12 01:44 | hard | learning/0 | 1.29 | 9.77 | 6분 | not_completed | not_review_phase, stability_below_threshold, fewer_success_dates, no_spaced_success |
| 10 | 2026-10-12 01:49 | hard | learning/0 | 1.29 | 9.83 | 6분 | not_completed | not_review_phase, stability_below_threshold, fewer_success_dates, no_spaced_success |
| 11 | 2026-10-12 01:55 | hard | learning/0 | 1.29 | 9.88 | 6분 | not_completed | not_review_phase, stability_below_threshold, fewer_success_dates, no_spaced_success |
| 12 | 2026-10-12 02:00 | hard | learning/0 | 1.29 | 9.90 | 6분 | not_completed | not_review_phase, stability_below_threshold, fewer_success_dates, no_spaced_success |
| 13 | 2026-10-12 02:06 | hard | learning/0 | 1.29 | 9.92 | 6분 | not_completed | not_review_phase, stability_below_threshold, fewer_success_dates, no_spaced_success |
| 14 | 2026-10-12 02:11 | hard | learning/0 | 1.29 | 9.93 | 6분 | not_completed | not_review_phase, stability_below_threshold, fewer_success_dates, no_spaced_success |
| 15 | 2026-10-12 02:17 | hard | learning/0 | 1.29 | 9.94 | 6분 | not_completed | not_review_phase, stability_below_threshold, fewer_success_dates, no_spaced_success |
| 16 | 2026-10-12 02:22 | hard | learning/0 | 1.29 | 9.95 | 6분 | not_completed | not_review_phase, stability_below_threshold, fewer_success_dates, no_spaced_success |
| 17 | 2026-10-12 02:28 | hard | learning/0 | 1.29 | 9.95 | 6분 | not_completed | not_review_phase, stability_below_threshold, fewer_success_dates, no_spaced_success |
| 18 | 2026-10-12 02:33 | hard | learning/0 | 1.29 | 9.95 | 6분 | not_completed | not_review_phase, stability_below_threshold, fewer_success_dates, no_spaced_success |
| 19 | 2026-10-12 02:39 | hard | learning/0 | 1.29 | 9.95 | 6분 | not_completed | not_review_phase, stability_below_threshold, fewer_success_dates, no_spaced_success |
| 20 | 2026-10-12 02:44 | hard | learning/0 | 1.29 | 9.95 | 6분 | not_completed | not_review_phase, stability_below_threshold, fewer_success_dates, no_spaced_success |
| 21 | 2026-10-12 02:50 | hard | learning/0 | 1.29 | 9.95 | 6분 | not_completed | not_review_phase, stability_below_threshold, fewer_success_dates, no_spaced_success |
| 22 | 2026-10-12 02:55 | hard | learning/0 | 1.29 | 9.96 | 6분 | not_completed | not_review_phase, stability_below_threshold, fewer_success_dates, no_spaced_success |
| 23 | 2026-10-12 03:01 | hard | learning/0 | 1.29 | 9.96 | 6분 | not_completed | not_review_phase, stability_below_threshold, fewer_success_dates, no_spaced_success |
| 24 | 2026-10-12 03:06 | hard | learning/0 | 1.29 | 9.96 | 6분 | not_completed | not_review_phase, stability_below_threshold, fewer_success_dates, no_spaced_success |
| 25 | 2026-10-12 03:12 | hard | learning/0 | 1.29 | 9.96 | 6분 | not_completed | not_review_phase, stability_below_threshold, fewer_success_dates, no_spaced_success |
| 26 | 2026-10-12 03:17 | hard | learning/0 | 1.29 | 9.96 | 6분 | not_completed | not_review_phase, stability_below_threshold, fewer_success_dates, no_spaced_success |
| 27 | 2026-10-12 03:23 | hard | learning/0 | 1.29 | 9.96 | 6분 | not_completed | not_review_phase, stability_below_threshold, fewer_success_dates, no_spaced_success |
| 28 | 2026-10-12 03:28 | hard | learning/0 | 1.29 | 9.96 | 6분 | not_completed | not_review_phase, stability_below_threshold, fewer_success_dates, no_spaced_success |
| 29 | 2026-10-12 03:34 | hard | learning/0 | 1.29 | 9.96 | 6분 | not_completed | not_review_phase, stability_below_threshold, fewer_success_dates, no_spaced_success |
| 30 | 2026-10-12 03:39 | hard | learning/0 | 1.29 | 9.96 | 6분 | not_completed | not_review_phase, stability_below_threshold, fewer_success_dates, no_spaced_success |
| 31 | 2026-10-12 03:45 | hard | learning/0 | 1.29 | 9.96 | 6분 | not_completed | not_review_phase, stability_below_threshold, fewer_success_dates, no_spaced_success |
| 32 | 2026-10-12 03:50 | hard | learning/0 | 1.29 | 9.96 | 6분 | not_completed | not_review_phase, stability_below_threshold, fewer_success_dates, no_spaced_success |
| 33 | 2026-10-12 03:56 | hard | learning/0 | 1.29 | 9.96 | 6분 | not_completed | not_review_phase, stability_below_threshold, fewer_success_dates, no_spaced_success |
| 34 | 2026-10-12 04:01 | hard | learning/0 | 1.29 | 9.96 | 6분 | not_completed | not_review_phase, stability_below_threshold, fewer_success_dates, no_spaced_success |
| 35 | 2026-10-12 04:07 | hard | learning/0 | 1.29 | 9.96 | 6분 | not_completed | not_review_phase, stability_below_threshold, fewer_success_dates, no_spaced_success |
| 36 | 2026-10-12 04:12 | hard | learning/0 | 1.29 | 9.96 | 6분 | not_completed | not_review_phase, stability_below_threshold, fewer_success_dates, no_spaced_success |
| 37 | 2026-10-12 04:18 | hard | learning/0 | 1.29 | 9.96 | 6분 | not_completed | not_review_phase, stability_below_threshold, fewer_success_dates, no_spaced_success |
| 38 | 2026-10-12 04:23 | hard | learning/0 | 1.29 | 9.96 | 6분 | not_completed | not_review_phase, stability_below_threshold, fewer_success_dates, no_spaced_success |
| 39 | 2026-10-12 04:29 | hard | learning/0 | 1.29 | 9.96 | 6분 | not_completed | not_review_phase, stability_below_threshold, fewer_success_dates, no_spaced_success |
| 40 | 2026-10-12 04:34 | hard | learning/0 | 1.29 | 9.96 | 6분 | not_completed | not_review_phase, stability_below_threshold, fewer_success_dates, no_spaced_success |

### hard_after_review: 보통 2회로 Review 진입 후 매번 어려움

| # | 평가 시각(UTC) | 평가 | 단계 | S(일) | D | 다음 간격 | 완료 판정 | 미충족 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 2026-10-12 01:00 | good | learning/1 | 2.31 | 2.12 | 10분 | not_completed | not_review_phase, stability_below_threshold, fewer_success_dates, no_spaced_success |
| 2 | 2026-10-12 01:10 | good | review | 2.31 | 2.11 | 2일 | not_completed | stability_below_threshold, fewer_success_dates, no_spaced_success |
| 3 | 2026-10-14 01:10 | hard | review | 7.52 | 4.75 | 8일 | not_completed | stability_below_threshold, no_spaced_success |
| 4 | 2026-10-22 01:10 | hard | review | 18.89 | 6.50 | 19일 | not_completed | stability_below_threshold |
| 5 | 2026-11-10 01:10 | hard | review | 35.84 | 7.66 | 36일 | completed | - |

### again_first_then_good: 첫 평가 다시, 이후 보통

| # | 평가 시각(UTC) | 평가 | 단계 | S(일) | D | 다음 간격 | 완료 판정 | 미충족 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 2026-10-12 01:00 | again | learning/0 | 0.21 | 6.41 | 1분 | not_completed | not_review_phase, stability_below_threshold, fewer_success_dates, no_spaced_success |
| 2 | 2026-10-12 01:01 | good | learning/1 | 0.25 | 6.40 | 10분 | not_completed | not_review_phase, stability_below_threshold, fewer_success_dates, no_spaced_success |
| 3 | 2026-10-12 01:11 | good | review | 0.28 | 6.39 | 1일 | not_completed | stability_below_threshold, fewer_success_dates, no_spaced_success |
| 4 | 2026-10-13 01:11 | good | review | 2.15 | 6.38 | 2일 | not_completed | stability_below_threshold, no_spaced_success |
| 5 | 2026-10-15 01:11 | good | review | 6.62 | 6.37 | 7일 | not_completed | stability_below_threshold, no_spaced_success |
| 6 | 2026-10-22 01:11 | good | review | 19.17 | 6.36 | 19일 | not_completed | stability_below_threshold |
| 7 | 2026-11-10 01:11 | good | review | 48.30 | 6.35 | 48일 | completed | - |

### good_with_mid_again: 보통, 4번째 평가만 다시, 이후 보통

| # | 평가 시각(UTC) | 평가 | 단계 | S(일) | D | 다음 간격 | 완료 판정 | 미충족 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 2026-10-12 01:00 | good | learning/1 | 2.31 | 2.12 | 10분 | not_completed | not_review_phase, stability_below_threshold, fewer_success_dates, no_spaced_success |
| 2 | 2026-10-12 01:10 | good | review | 2.31 | 2.11 | 2일 | not_completed | stability_below_threshold, fewer_success_dates, no_spaced_success |
| 3 | 2026-10-14 01:10 | good | review | 10.97 | 2.10 | 11일 | not_completed | stability_below_threshold, no_spaced_success |
| 4 | 2026-10-25 01:10 | again | relearning/0 | 1.54 | 7.39 | 10분 | not_completed | not_review_phase, stability_below_threshold, fewer_success_dates, no_spaced_success |
| 5 | 2026-10-25 01:20 | good | review | 1.57 | 7.38 | 2일 | not_completed | stability_below_threshold, fewer_success_dates, no_spaced_success |
| 6 | 2026-10-27 01:20 | good | review | 4.93 | 7.37 | 5일 | not_completed | stability_below_threshold, no_spaced_success |
| 7 | 2026-11-01 01:20 | good | review | 12.41 | 7.35 | 12일 | not_completed | stability_below_threshold, no_spaced_success |
| 8 | 2026-11-13 01:20 | good | review | 28.05 | 7.34 | 28일 | not_completed | stability_below_threshold |
| 9 | 2026-12-11 01:20 | good | review | 59.74 | 7.33 | 60일 | completed | - |

### again_after_completion: 보통으로 완료(4번째) 직후 5번째 다시, 이후 보통으로 재완료까지

| # | 평가 시각(UTC) | 평가 | 단계 | S(일) | D | 다음 간격 | 완료 판정 | 미충족 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 2026-10-12 01:00 | good | learning/1 | 2.31 | 2.12 | 10분 | not_completed | not_review_phase, stability_below_threshold, fewer_success_dates, no_spaced_success |
| 2 | 2026-10-12 01:10 | good | review | 2.31 | 2.11 | 2일 | not_completed | stability_below_threshold, fewer_success_dates, no_spaced_success |
| 3 | 2026-10-14 01:10 | good | review | 10.97 | 2.10 | 11일 | not_completed | stability_below_threshold, no_spaced_success |
| 4 | 2026-10-25 01:10 | good | review | 46.32 | 2.10 | 46일 | completed | - |
| 5 | 2026-12-10 01:10 | again | relearning/0 | 2.93 | 7.39 | 10분 | not_completed | not_review_phase, stability_below_threshold, fewer_success_dates, no_spaced_success |
| 6 | 2026-12-10 01:20 | good | review | 2.93 | 7.38 | 3일 | not_completed | stability_below_threshold, fewer_success_dates, no_spaced_success |
| 7 | 2026-12-13 01:20 | good | review | 7.80 | 7.36 | 8일 | not_completed | stability_below_threshold, no_spaced_success |
| 8 | 2026-12-21 01:20 | good | review | 18.85 | 7.35 | 19일 | not_completed | stability_below_threshold |
| 9 | 2027-01-09 01:20 | good | review | 41.70 | 7.34 | 42일 | completed | - |

### hard_good_alternate: 어려움·보통 번갈아

| # | 평가 시각(UTC) | 평가 | 단계 | S(일) | D | 다음 간격 | 완료 판정 | 미충족 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 2026-10-12 01:00 | hard | learning/0 | 1.29 | 5.11 | 6분 | not_completed | not_review_phase, stability_below_threshold, fewer_success_dates, no_spaced_success |
| 2 | 2026-10-12 01:05 | good | learning/1 | 1.34 | 5.10 | 10분 | not_completed | not_review_phase, stability_below_threshold, fewer_success_dates, no_spaced_success |
| 3 | 2026-10-12 01:15 | hard | learning/1 | 1.34 | 6.73 | 10분 | not_completed | not_review_phase, stability_below_threshold, fewer_success_dates, no_spaced_success |
| 4 | 2026-10-12 01:25 | good | review | 1.38 | 6.72 | 1일 | not_completed | stability_below_threshold, fewer_success_dates, no_spaced_success |
| 5 | 2026-10-13 01:25 | hard | review | 2.80 | 7.81 | 3일 | not_completed | stability_below_threshold, no_spaced_success |
| 6 | 2026-10-16 01:25 | good | review | 7.06 | 7.80 | 7일 | not_completed | stability_below_threshold, no_spaced_success |
| 7 | 2026-10-23 01:25 | hard | review | 12.32 | 8.52 | 12일 | not_completed | stability_below_threshold |
| 8 | 2026-11-04 01:25 | good | review | 22.94 | 8.51 | 23일 | not_completed | stability_below_threshold |
| 9 | 2026-11-27 01:25 | hard | review | 33.95 | 9.00 | 34일 | completed | - |

### good_late_3d: 보통, 매번 due보다 3일 늦게

| # | 평가 시각(UTC) | 평가 | 단계 | S(일) | D | 다음 간격 | 완료 판정 | 미충족 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 2026-10-12 01:00 | good | learning/1 | 2.31 | 2.12 | 10분 | not_completed | not_review_phase, stability_below_threshold, fewer_success_dates, no_spaced_success |
| 2 | 2026-10-15 01:10 | good | review | 13.83 | 2.11 | 14일 | not_completed | stability_below_threshold, no_spaced_success |
| 3 | 2026-11-01 01:10 | good | review | 63.20 | 2.10 | 63일 | completed | - |

### same_day_repeat: 같은 날 10분마다 보통 20회 (그 뒤 관측 종료)

| # | 평가 시각(UTC) | 평가 | 단계 | S(일) | D | 다음 간격 | 완료 판정 | 미충족 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 2026-10-12 01:00 | good | learning/1 | 2.31 | 2.12 | 10분 | not_completed | not_review_phase, stability_below_threshold, fewer_success_dates, no_spaced_success |
| 2 | 2026-10-12 01:10 | good | review | 2.31 | 2.11 | 2일 | not_completed | stability_below_threshold, fewer_success_dates, no_spaced_success |
| 3 | 2026-10-12 01:20 | good | review | 2.31 | 2.10 | 2일 | not_completed | stability_below_threshold, fewer_success_dates, no_spaced_success |
| 4 | 2026-10-12 01:30 | good | review | 2.31 | 2.10 | 2일 | not_completed | stability_below_threshold, fewer_success_dates, no_spaced_success |
| 5 | 2026-10-12 01:40 | good | review | 2.31 | 2.09 | 2일 | not_completed | stability_below_threshold, fewer_success_dates, no_spaced_success |
| 6 | 2026-10-12 01:50 | good | review | 2.31 | 2.08 | 2일 | not_completed | stability_below_threshold, fewer_success_dates, no_spaced_success |
| 7 | 2026-10-12 02:00 | good | review | 2.31 | 2.08 | 2일 | not_completed | stability_below_threshold, fewer_success_dates, no_spaced_success |
| 8 | 2026-10-12 02:10 | good | review | 2.31 | 2.07 | 2일 | not_completed | stability_below_threshold, fewer_success_dates, no_spaced_success |
| 9 | 2026-10-12 02:20 | good | review | 2.31 | 2.06 | 2일 | not_completed | stability_below_threshold, fewer_success_dates, no_spaced_success |
| 10 | 2026-10-12 02:30 | good | review | 2.31 | 2.06 | 2일 | not_completed | stability_below_threshold, fewer_success_dates, no_spaced_success |
| 11 | 2026-10-12 02:40 | good | review | 2.31 | 2.05 | 2일 | not_completed | stability_below_threshold, fewer_success_dates, no_spaced_success |
| 12 | 2026-10-12 02:50 | good | review | 2.31 | 2.04 | 2일 | not_completed | stability_below_threshold, fewer_success_dates, no_spaced_success |
| 13 | 2026-10-12 03:00 | good | review | 2.31 | 2.04 | 2일 | not_completed | stability_below_threshold, fewer_success_dates, no_spaced_success |
| 14 | 2026-10-12 03:10 | good | review | 2.31 | 2.03 | 2일 | not_completed | stability_below_threshold, fewer_success_dates, no_spaced_success |
| 15 | 2026-10-12 03:20 | good | review | 2.31 | 2.02 | 2일 | not_completed | stability_below_threshold, fewer_success_dates, no_spaced_success |
| 16 | 2026-10-12 03:30 | good | review | 2.31 | 2.02 | 2일 | not_completed | stability_below_threshold, fewer_success_dates, no_spaced_success |
| 17 | 2026-10-12 03:40 | good | review | 2.31 | 2.01 | 2일 | not_completed | stability_below_threshold, fewer_success_dates, no_spaced_success |
| 18 | 2026-10-12 03:50 | good | review | 2.31 | 2.00 | 2일 | not_completed | stability_below_threshold, fewer_success_dates, no_spaced_success |
| 19 | 2026-10-12 04:00 | good | review | 2.31 | 2.00 | 2일 | not_completed | stability_below_threshold, fewer_success_dates, no_spaced_success |
| 20 | 2026-10-12 04:10 | good | review | 2.31 | 1.99 | 2일 | not_completed | stability_below_threshold, fewer_success_dates, no_spaced_success |
