import { AppEmptyState, BrandSectionBadge } from "./BrandElements";
import { getDisplayMeaning } from "./shared";
import {
  BookIcon,
  BookmarkIcon,
  CardFileIcon,
  ClockIcon,
  PencilIcon,
  ShieldIcon,
  SparkleIcon,
} from "./icons";
import type { DeckStats, StudyStats, VocabItem } from "./types";

type StudyLogPageProps = {
  stats: StudyStats | null;
  isStatsLoading: boolean;
  statsMessage: string;
  recentWords: VocabItem[];
  hardWords: VocabItem[];
  isWordsLoading: boolean;
  onGoToVocab: () => void;
  onGoToReading: () => void;
};

// ---------------------------------------------------------------------------
// StudyLogHero -- title + one-line description only, no stat/number here.
// ---------------------------------------------------------------------------
function StudyLogHero() {
  return (
    <div className="reading-hero">
      <h2 className="reading-hero-title">학습 통계</h2>
      <p className="reading-hero-subtitle">오늘까지의 학습 현황을 한눈에 확인하세요.</p>
    </div>
  );
}

// ---------------------------------------------------------------------------
// TodayStudyMemo -- at most 3 numbers, large: 오늘 복습 / 최근 담은 단어 /
// 어려운 단어. Deliberately not a 6+-cell stat grid.
// ---------------------------------------------------------------------------
function TodayStudyMemo({
  dueTodayCount,
  recentCount,
  hardCount,
}: {
  dueTodayCount: number;
  recentCount: number;
  hardCount: number;
}) {
  return (
    <section className="study-log-entry today-study-memo">
      <h3 className="records-log-title">오늘 학습</h3>
      <div className="records-today-row">
        <span className="home-summary-chip">
          <ClockIcon className="home-summary-chip-icon" />
          <span>오늘 복습</span>
          <strong>{dueTodayCount}</strong>
        </span>
        <span className="home-summary-chip">
          <BookmarkIcon className="home-summary-chip-icon" />
          <span>최근 담은 단어</span>
          <strong>{recentCount}</strong>
        </span>
        <span className="home-summary-chip">
          <PencilIcon className="home-summary-chip-icon" />
          <span>어려운 단어</span>
          <strong>{hardCount}</strong>
        </span>
      </div>
    </section>
  );
}

// ---------------------------------------------------------------------------
// StudyTimeline -- short diary-style lines instead of another stat block,
// so the same underlying numbers also read as "what happened", not just
// counts.
// ---------------------------------------------------------------------------
type JournalEntry = { icon: typeof ClockIcon; text: string };

function StudyTimeline({ entries }: { entries: JournalEntry[] }) {
  if (entries.length === 0) {
    return null;
  }
  return (
    <section className="study-log-entry study-timeline">
      <h3 className="records-log-title">학습 일지</h3>
      <div className="study-log-journal-list">
        {entries.map((entry, index) => (
          <p className="study-log-journal-line" key={index}>
            <entry.icon className="study-log-journal-icon" />
            {entry.text}
          </p>
        ))}
      </div>
    </section>
  );
}

// ---------------------------------------------------------------------------
// DeckProgressJournal -- each deck is a notebook progress row (name,
// progress bar, 오늘 복습 수, 모르는 단어 수), not a data-table row. Deeper
// numbers (전체/아는/헷갈리는 단어) stay behind a small "자세히 보기"
// disclosure.
// ---------------------------------------------------------------------------
function DeckProgressJournal({ deckStats }: { deckStats: DeckStats[] }) {
  if (deckStats.length === 0) {
    return null;
  }
  return (
    <section className="study-log-entry deck-progress-journal">
      <h3 className="records-log-title">서가별 통계</h3>
      <div className="records-deck-log">
        {deckStats.map((deck) => (
          <div className="records-deck-row paper-corner" key={deck.deck_id}>
            <div className="records-deck-row-head">
              <strong>{deck.deck_name}</strong>
              <span>{Math.round(deck.learned_rate * 100)}%</span>
            </div>
            <div className="progress-bar records-deck-progress">
              <div style={{ width: `${Math.round(deck.learned_rate * 100)}%` }} />
            </div>
            <div className="records-deck-row-primary-meta">
              <span className="records-deck-row-due">오늘 복습 {deck.due_today_count}개</span>
              <span className="records-deck-row-unknown">모르는 단어 {deck.unknown_count}개</span>
            </div>
            <details className="records-deck-detail">
              <summary>자세히 보기</summary>
              <p className="records-deck-row-meta">
                전체 {deck.total_count} · 아는 단어 {deck.known_count} · 헷갈리는 단어{" "}
                {deck.uncertain_count}
              </p>
            </details>
          </div>
        ))}
      </div>
    </section>
  );
}

// ---------------------------------------------------------------------------
// StudyLogEmptyState -- small bookmark/notebook illustration + short copy +
// one CTA, for a brand-new account with no study history yet.
// ---------------------------------------------------------------------------
function StudyLogEmptyState({ onGoToReading }: { onGoToReading: () => void }) {
  return (
    <AppEmptyState
      mood="empty"
      moodSize="lg"
      title="아직 기록이 없어요."
      description="원문을 읽고 첫 단어를 담아보세요."
    >
      <button type="button" className="ghost-button compact-button" onClick={onGoToReading}>
        <SparkleIcon className="button-icon" />
        원문 읽기 시작
      </button>
    </AppEmptyState>
  );
}

// ---------------------------------------------------------------------------
// StudyLogPage -- composes the above into a study log / library journal,
// not a stats dashboard. All values come from the existing StudyStats/
// VocabItem data already fetched in page.tsx (loadInfoStats/
// loadInfoWordHighlights) -- no new API calls, no route change.
// ---------------------------------------------------------------------------
export function StudyLogPage({
  stats,
  isStatsLoading,
  statsMessage,
  recentWords,
  hardWords,
  isWordsLoading,
  onGoToVocab,
  onGoToReading,
}: StudyLogPageProps) {
  const hasStats = Boolean(stats);
  const isEmpty = !isStatsLoading && !hasStats && !statsMessage;

  const journalEntries: JournalEntry[] = [];
  if (stats) {
    journalEntries.push({
      icon: ClockIcon,
      text:
        stats.due_today_count > 0
          ? `오늘 복습할 단어가 ${stats.due_today_count}개 있어요.`
          : "오늘은 복습할 단어가 없어요.",
    });
  }
  if (recentWords.length > 0) {
    journalEntries.push({
      icon: BookmarkIcon,
      text: `최근 담은 단어 ${recentWords.length}개가 노트에 쌓였어요.`,
    });
  } else if (stats) {
    journalEntries.push({
      icon: BookmarkIcon,
      text: "원문을 읽고 새 단어를 담아보세요.",
    });
  }
  if (hardWords.length > 0) {
    journalEntries.push({
      icon: PencilIcon,
      text: `어려운 단어 ${hardWords.length}개는 다시 나타나요.`,
    });
  }

  return (
    <section className="tab-panel study-log-page" aria-live="polite">
      <StudyLogHero />

      {isStatsLoading && !stats ? (
        <p className="muted-text">학습 기록을 불러오는 중입니다.</p>
      ) : null}
      {statsMessage ? <p className="message message--info">{statsMessage}</p> : null}

      {isEmpty ? <StudyLogEmptyState onGoToReading={onGoToReading} /> : null}

      {hasStats && stats ? (
        <>
          <TodayStudyMemo
            dueTodayCount={stats.due_today_count}
            recentCount={recentWords.length}
            hardCount={hardWords.length}
          />
          <StudyTimeline entries={journalEntries} />
          <DeckProgressJournal deckStats={stats.deck_stats} />
        </>
      ) : null}

      {hasStats ? (
        <section className="study-log-entry">
          <h3 className="records-log-title">
            <BrandSectionBadge icon={BookmarkIcon} />
            최근 담은 단어
          </h3>
          {isWordsLoading && recentWords.length === 0 ? (
            <p className="muted-text">불러오는 중...</p>
          ) : recentWords.length > 0 ? (
            <div className="records-word-log">
              {recentWords.map((item) => (
                <div className="records-word-row paper-corner" key={item.id}>
                  <span className="records-word-surface">{item.surface}</span>
                  {item.reading && item.reading !== item.surface ? (
                    <span className="records-word-reading">{item.reading}</span>
                  ) : null}
                  <span className="records-word-meaning">
                    {getDisplayMeaning(item.meaning_ko)}
                  </span>
                </div>
              ))}
            </div>
          ) : (
            <p className="muted-text">아직 담은 단어가 없어요.</p>
          )}
        </section>
      ) : null}

      {hasStats ? (
        <section className="study-log-entry">
          <h3 className="records-log-title">
            <BrandSectionBadge icon={PencilIcon} />
            자주 틀린 단어
          </h3>
          {isWordsLoading && hardWords.length === 0 ? (
            <p className="muted-text">불러오는 중...</p>
          ) : hardWords.length > 0 ? (
            <div className="records-word-log">
              {hardWords.map((item) => (
                <div className="records-word-row paper-corner" key={item.id}>
                  <span className="records-word-surface">{item.surface}</span>
                  {item.reading && item.reading !== item.surface ? (
                    <span className="records-word-reading">{item.reading}</span>
                  ) : null}
                  <span className="records-word-meaning">
                    {getDisplayMeaning(item.meaning_ko)}
                  </span>
                  <span className="records-word-wrong-badge">다시 {item.wrong_count}회</span>
                </div>
              ))}
            </div>
          ) : (
            <p className="muted-text">아직 자주 틀린 단어가 없어요.</p>
          )}
        </section>
      ) : null}

      {hasStats ? (
        <button type="button" className="ghost-button compact-button" onClick={onGoToVocab}>
          <CardFileIcon className="button-icon" />
          어휘 노트 전체 보기
        </button>
      ) : null}

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
