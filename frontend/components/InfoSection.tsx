import { BrandSectionBadge } from "./BrandElements";
import { BookIcon, ShieldIcon } from "./icons";
import { StatsPanel } from "./StatsPanel";
import type { StudyStats } from "./types";

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
    <section className="tab-panel records-panel" aria-live="polite">
      <div className="reading-hero">
        <h2 className="reading-hero-title">기록</h2>
        <p className="reading-hero-subtitle">
          오늘의 학습 흐름과 복습 상태를 확인하세요.
        </p>
      </div>

      <StatsPanel
        title="전체 학습 통계"
        stats={stats}
        isLoading={isStatsLoading}
        message={statsMessage}
        showDeckStats
      />

      <div className="info-panel">
        <section className="panel-card note-card info-panel-card">
          <div className="panel-card-header">
            <h2 className="panel-card-title">
              <BrandSectionBadge icon={ShieldIcon} />
              저장 정책
            </h2>
          </div>
          <p className="panel-card-description">
            원문 전체는 저장하지 않아요. 단어와 짧은 예문만 노트에 남습니다.
          </p>
        </section>
      </div>

      <p className="info-strip">
        <BookIcon className="info-strip-icon" />
        사전 뜻풀이는 JMdict/EDRDG, Kaikki/Wiktionary 데이터를 참고합니다.
      </p>
    </section>
  );
}
