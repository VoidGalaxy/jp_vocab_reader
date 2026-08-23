import { AppEmptyState } from "./BrandElements";
import { ShioriStamp } from "./Shiori";
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
// LogbookHeader -- title/subtitle plus the "오늘" numbers stamped directly
// under it. Phase 161: the three numbers used to be their own titled section
// ("오늘 학습" h3 + a row below it), which read as a small stat block bolted
// onto the top of the page. They're postmarks on the page itself now -- no
// section heading of their own, no dedicated <section> wrapper.
// ---------------------------------------------------------------------------
function LogbookHeader({
  dueTodayCount,
  recentCount,
  hardCount,
}: {
  dueTodayCount: number;
  recentCount: number;
  hardCount: number;
}) {
  return (
    <header className="stats-logbook-header">
      <div className="study-log-hero-row">
        <h2 className="reading-hero-title">학습 통계</h2>
        <ShioriStamp variant="success" label="학습 기록" />
      </div>
      <p className="reading-hero-subtitle">오늘까지의 학습 현황을 한눈에 확인하세요.</p>
      <div className="stats-today-stamps">
        <span className="study-stamp-tag">
          <ClockIcon className="study-stamp-tag-icon" />
          <span>오늘 복습</span>
          <strong>{dueTodayCount}</strong>
        </span>
        <span className="study-stamp-tag">
          <BookmarkIcon className="study-stamp-tag-icon" />
          <span>최근 담은 단어</span>
          <strong>{recentCount}</strong>
        </span>
        <span className="study-stamp-tag">
          <PencilIcon className="study-stamp-tag-icon" />
          <span>어려운 단어</span>
          <strong>{hardCount}</strong>
        </span>
      </div>
    </header>
  );
}

// ---------------------------------------------------------------------------
// StudyTimeline -- diary-style lines ruled directly on the logbook page (no
// border/background of its own anymore -- see .study-diary-sheet, Phase
// 161: dropped the box chrome so this reads as ruled paper on the same page
// as everything else, not a card floating on top of it).
// ---------------------------------------------------------------------------
type JournalEntry = { icon: typeof ClockIcon; text: string };

function StudyTimeline({ entries }: { entries: JournalEntry[] }) {
  if (entries.length === 0) {
    return null;
  }
  return (
    <section className="study-log-entry study-timeline">
      <h3 className="stats-section-tab">학습 일지</h3>
      <div className="study-diary-sheet">
        {entries.map((entry, index) => (
          <p className="study-diary-line" key={index}>
            <entry.icon className="study-diary-line-icon" />
            {entry.text}
          </p>
        ))}
      </div>
    </section>
  );
}

// ---------------------------------------------------------------------------
// DeckProgressJournal -- same ledger rows as before, now unboxed (Phase 161:
// .records-deck-ledger lost its own border/background) so the rows sit
// directly on the logbook page instead of inside a second nested card.
// ---------------------------------------------------------------------------
function DeckProgressJournal({ deckStats }: { deckStats: DeckStats[] }) {
  if (deckStats.length === 0) {
    return null;
  }
  return (
    <section className="study-log-entry deck-progress-journal">
      <h3 className="stats-section-tab">서가별 통계</h3>
      <div className="records-deck-ledger">
        {deckStats.map((deck) => (
          <div className="records-deck-ledger-row" key={deck.deck_id}>
            <div className="records-deck-row-head">
              <strong>{deck.deck_name}</strong>
              <span>{Math.round(deck.learned_rate * 100)}%</span>
            </div>
            <div className="records-deck-progress-line">
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
// WordSlip -- Phase 161: replaces the old "aside" widget-panel sections.
// Each of 최근 담은 단어/자주 틀린 단어 is now its own small pinned note slip
// (washi tape + slight tilt, same pinned-note family .study-stamp-tag and
// Vocab/Home's own sticky notes already use) resting on the logbook page
// next to the ledger, not a bordered sidebar column of app-style cards.
// ---------------------------------------------------------------------------
function WordSlip({
  title,
  icon: Icon,
  isLoading,
  words,
  emptyText,
  showWrongCount,
}: {
  title: string;
  icon: typeof ClockIcon;
  isLoading: boolean;
  words: VocabItem[];
  emptyText: string;
  showWrongCount?: boolean;
}) {
  return (
    <div className="stats-word-slip">
      <h3 className="stats-section-tab stats-section-tab--slip">
        <Icon className="stats-section-tab-icon" />
        {title}
      </h3>
      {isLoading && words.length === 0 ? (
        <p className="muted-text">불러오는 중...</p>
      ) : words.length > 0 ? (
        <div className="stats-word-slip-list">
          {words.map((item) => (
            <div className="stats-word-slip-row" key={item.id}>
              <span className="records-word-surface">{item.surface}</span>
              {item.reading && item.reading !== item.surface ? (
                <span className="records-word-reading">{item.reading}</span>
              ) : null}
              <span className="records-word-meaning">{getDisplayMeaning(item.meaning_ko)}</span>
              {showWrongCount ? (
                <span className="records-word-wrong-badge">다시 {item.wrong_count}회</span>
              ) : null}
            </div>
          ))}
        </div>
      ) : (
        <p className="muted-text">{emptyText}</p>
      )}
    </div>
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
// StudyLogPage -- Phase 161 (Study Logbook full reconstruction): the whole
// tab is now one physical ledger book (.stats-logbook-page) instead of a
// main-column-plus-widget-sidebar dashboard. Today's numbers are postmark
// stamps on the header, the diary and deck ledger sit unboxed on the page,
// and recent/difficult words are two small note slips resting beside the
// ledger (below it on narrow screens) rather than a separate panel. All
// values still come from the existing StudyStats/VocabItem data already
// fetched in page.tsx -- no new API calls, no route change.
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
      <div className="stats-logbook-scene">
        <div className="stats-logbook-page paper-corner">
          <LogbookHeader
            dueTodayCount={stats?.due_today_count ?? 0}
            recentCount={recentWords.length}
            hardCount={hardWords.length}
          />

          {isStatsLoading && !stats ? (
            <p className="muted-text">학습 기록을 불러오는 중입니다.</p>
          ) : null}
          {statsMessage ? <p className="message message--info">{statsMessage}</p> : null}

          {isEmpty ? <StudyLogEmptyState onGoToReading={onGoToReading} /> : null}

          {hasStats && stats ? (
            <div className="stats-logbook-spread">
              <div className="stats-logbook-leaf stats-logbook-leaf--main">
                <StudyTimeline entries={journalEntries} />
                <DeckProgressJournal deckStats={stats.deck_stats} />
              </div>

              <div className="stats-logbook-gutter" aria-hidden="true" />

              <div className="stats-logbook-leaf stats-logbook-leaf--slips">
                <WordSlip
                  title="최근 담은 단어"
                  icon={BookmarkIcon}
                  isLoading={isWordsLoading}
                  words={recentWords}
                  emptyText="아직 담은 단어가 없어요."
                />
                <WordSlip
                  title="자주 틀린 단어"
                  icon={PencilIcon}
                  isLoading={isWordsLoading}
                  words={hardWords}
                  emptyText="아직 자주 틀린 단어가 없어요."
                  showWrongCount
                />
              </div>
            </div>
          ) : null}

          {hasStats ? (
            <button type="button" className="ghost-button compact-button" onClick={onGoToVocab}>
              <CardFileIcon className="button-icon" />
              어휘 노트 전체 보기
            </button>
          ) : null}

          <footer className="stats-logbook-footer">
            <p className="stats-logbook-footer-line">
              <ShieldIcon className="info-strip-icon" />
              원문 전체는 저장하지 않아요. 단어와 짧은 예문만 노트에 남아요.
            </p>
            <p className="stats-logbook-footer-line">
              <BookIcon className="info-strip-icon" />
              사전 뜻풀이는 JMdict/EDRDG, Kaikki/Wiktionary 데이터를 참고합니다.
            </p>
          </footer>
        </div>
      </div>
    </section>
  );
}
