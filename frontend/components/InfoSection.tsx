import { BrandSectionBadge } from "./BrandElements";
import { BookIcon, CheckCircleIcon, InfoIcon, ShieldIcon, SparkleIcon } from "./icons";
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
    <section className="tab-panel" aria-live="polite">
      <StatsPanel
        title="전체 학습 통계"
        stats={stats}
        isLoading={isStatsLoading}
        message={statsMessage}
        showDeckStats
      />

      <div className="info-panel">
        <section className="panel-card info-panel-card">
          <div className="panel-card-header">
            <h2 className="panel-card-title">
              <BrandSectionBadge icon={InfoIcon} />
              서비스 개요
            </h2>
          </div>
          <p className="panel-card-description">
            일본어 원문을 읽으며 모르는 단어를 저장하고, 문맥 예문과 함께
            복습하는 학습 노트입니다.
          </p>
        </section>

        <section className="panel-card note-card info-panel-card">
          <div className="panel-card-header">
            <h2 className="panel-card-title">
              <BrandSectionBadge icon={ShieldIcon} />
              저장 정책
            </h2>
          </div>
          <p className="panel-card-description">
            원문 전체는 저장하지 않아요. 단어와 짧은 예문만 단어장에 남습니다.
          </p>
        </section>

        <section className="panel-card info-panel-card">
          <div className="panel-card-header">
            <h2 className="panel-card-title">
              <BrandSectionBadge icon={CheckCircleIcon} />
              현재 기능
            </h2>
          </div>
          <ul className="info-panel-list">
            <li>원문 분석, 사용자 정의 용어 우선 매칭, 예문 추출</li>
            <li>카드 기반 단어 분류와 분류 진행상태 임시 저장</li>
            <li>덱별 단어장, 검색/필터/정렬, 직접 추가/수정</li>
            <li>모르는 단어와 헷갈리는 단어 중심의 플래시카드 복습</li>
            <li>CSV/JSON 백업과 공개 공유 덱 가져오기</li>
          </ul>
        </section>

        <section className="panel-card note-card info-panel-card">
          <div className="panel-card-header">
            <h2 className="panel-card-title">
              <BrandSectionBadge icon={BookIcon} />
              사전 데이터 출처
            </h2>
          </div>
          <p className="panel-card-description">
            JMdict/EDICT project by EDRDG, Kaikki/Wiktionary 데이터를
            참고합니다. 사용자 정의 용어와 개인 단어장은 별도로 저장됩니다.
          </p>
        </section>

        <section className="panel-card info-panel-card">
          <div className="panel-card-header">
            <h2 className="panel-card-title">
              <BrandSectionBadge icon={SparkleIcon} />
              앞으로 추가할 기능
            </h2>
          </div>
          <ul className="info-panel-list">
            <li>사전 데이터 확장</li>
            <li>고급 간격 반복과 학습 통계</li>
            <li>Anki 전용 내보내기 검토</li>
            <li>문장/문단 단위 독해 보조 기능 검토</li>
          </ul>
        </section>
      </div>
    </section>
  );
}
