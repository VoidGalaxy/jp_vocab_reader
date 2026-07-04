import type { StudyStats } from "./types";
import { StatsPanel } from "./StatsPanel";

type InfoSectionProps = {
  stats: StudyStats | null;
  isStatsLoading: boolean;
  statsMessage: string;
};

export function InfoSection({
  stats,
  isStatsLoading,
  statsMessage,
}: InfoSectionProps) {
  return (
    <section className="tab-panel">
      <StatsPanel
        title="전체 학습 통계"
        stats={stats}
        isLoading={isStatsLoading}
        message={statsMessage}
        showDeckStats
      />

      <div className="info-panel">
      <div>
        <h2>서비스 개요</h2>
        <p>
          이 앱은 일본어 원서와 웹소설 학습자를 위한 자동 단어장
          생성기입니다. 원문을 분석해 단어, 읽기, 품사, 뜻, 예문을 정리하고
          앱 안에서 바로 복습할 수 있게 합니다.
        </p>
      </div>

      <div>
        <h2>저장 정책</h2>
        <p>
          사용자가 붙여넣은 원문 전체는 DB에 저장하지 않습니다. 사용자가
          저장한 단어와 해당 단어가 나온 짧은 예문만 단어장 데이터로
          보관합니다.
        </p>
      </div>

      <div>
        <h2>현재 기능</h2>
        <ul>
          <li>원문 분석, 사용자 정의 용어 우선 매칭, 예문 추출</li>
          <li>카드 기반 단어 분류와 분류 진행상태 임시 저장</li>
          <li>덱별 단어장, 검색/필터/정렬, 직접 추가/수정</li>
          <li>모르는 단어와 헷갈리는 단어 중심의 플래시카드 복습</li>
          <li>CSV/JSON 백업과 공개 공유 덱 가져오기</li>
        </ul>
      </div>

      <div>
        <h2>TODO</h2>
        <ul>
          <li>사전 데이터 확장</li>
          <li>고급 간격 반복과 학습 통계</li>
          <li>Anki 전용 내보내기 검토</li>
          <li>문장/문단 단위 독해 보조 기능 검토</li>
        </ul>
      </div>
      </div>
    </section>
  );
}
