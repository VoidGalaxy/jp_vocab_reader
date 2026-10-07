# 에셋·QA 자료 정리 후보

2026-10-07 조사. **목록만 작성했으며 삭제·이동·커밋 등록하지 않았다.**
제품 코드 기준 `0fb5a0f`. 현재 사용하지 않는 것과 보존 가치가 없는 것은 같은 뜻이 아니다.

## 과거 배포 에셋

`frontend/app`과 `frontend/components`에서 아래 파일명 참조가 없음을 확인했다. manifest와 설계 문서에는 참조가 남아 있다. 삭제 전 전체 코드·빌드·문서 참조를 다시 조사하고 승인받는다.

| 경로 (`frontend/public/brand/decor/` 기준) | 크기 (bytes) | 관리 상태 |
| --- | ---: | --- |
| `v2/v2-classify-card-desk-desktop-16x9.webp` | 186816 | 추적, 과거 분류 장면 |
| `v2/v2-classify-card-desk-mobile-9x16.webp` | 226742 | 추적, 과거 분류 장면 |
| `v2/v2-stats-logbook-desktop-16x9.webp` | 99962 | 추적, 과거 통계 장면 |
| `v2/v2-stats-logbook-mobile-9x16.webp` | 106736 | 추적, 과거 통계 장면 |

새 제본/종이 타일, C 읽기 wide/tall WebP 등 현재 사용 중인 파일은 이 목록의 삭제 대상이 아니다.

## 사용자 작업으로 보존한 미추적 PNG

`frontend/public/brand/decor/v4/` 아래의 여섯 파일이다. 앱 코드의 파일명 참조는 없지만 일부는 manifest에 기록되어 있다. 소유·원본 가치가 확인되기 전 그대로 둔다.

| 파일 | 크기 (bytes) |
| --- | ---: |
| `v4-reading-open-book-desktop-matte-seam.png` | 2947906 |
| `v4-reading-open-book-desktop-paper-b.png` | 3112790 |
| `v4-reading-open-book-desktop-tall-matte-seam.png` | 2283815 |
| `v4-reading-open-book-desktop-tall-paper-b.png` | 3345587 |
| `v4-reading-quiet-folio-tall.png` | 1385883 |
| `v4-reading-quiet-folio-wide.png` | 1407834 |

## QA·시안·캐시

- `references/mockups/`: 탭별 방향 탐색·승인·게이트 캡처. 대부분 미추적이고 클라우드에는 자동 전달되지 않는다.
- `references/plans/`: 학습 계획 계약·게이트·이전 분류 관련 기록. 전부를 제품 커밋에 넣지 않는다.
- `frontend/tsconfig.tsbuildinfo`: 빌드 캐시, 제품 커밋 제외. 원본 작업과 섞어 삭제하지 않는다.
- `.next`, `.venv`, `node_modules`, DB와 `.env`: 일반 작업 인계 패키지와 커밋에서 제외한다.

## 나중에 정리하는 순서

1. 승인된 최종 캡처·계약·재현 스크립트의 보존 목적과 저장 위치를 정한다.
2. 보고서에 계정 정보·토큰·DB·원문·실제 연결값이 없는지 검토한다.
3. 미추적 사용자 원본과 재생성 가능한 출력물을 구분하고, 필요한 인계 파일만 선별한다.
4. 사용하지 않는 추적 에셋은 문서·manifest·기능 참조를 함께 확인한 뒤 별도 삭제 승인으로 처리한다.
5. 경로·파일 목록을 명시하고 해당 범위만 정리한다. 광범위한 clean/삭제 명령은 사용하지 않는다.
