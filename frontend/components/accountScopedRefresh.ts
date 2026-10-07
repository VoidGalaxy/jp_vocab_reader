// 계정 범위 자료 전체 갱신(로그인·로그아웃·만료·첫 진입).
//
// 규칙:
// - 시작할 때의 계정 epoch을 기록하고, 각 단계를 기다린 직후 epoch이
//   바뀌었으면 남은 단계를 실행하지 않는다. 다음 계정의 갱신이 따로 돈다.
// - 이 흐름은 복습 세션을 건드리지 않는다. 세션 초기화는 계정 경계에서
//   동기로 한 번만 한다(page.tsx resetStatsForAccountChange). 그래서 갱신이
//   끝나기 전에 시작한 새 세션이 늦게 끝난 갱신에 지워지지 않는다.
//
// React와 무관한 순수 모듈: 테스트는 가짜 단계로 돌린다.

export type AccountScopedStep = () => Promise<unknown>;

// 모든 단계를 같은 계정에서 마치면 true, 중간에 계정이 바뀌어 멈추면 false.
export async function runAccountScopedRefresh(
  getAccountEpoch: () => number,
  steps: readonly AccountScopedStep[],
): Promise<boolean> {
  const epoch = getAccountEpoch();
  for (const step of steps) {
    if (epoch !== getAccountEpoch()) return false;
    await step();
  }
  return epoch === getAccountEpoch();
}
