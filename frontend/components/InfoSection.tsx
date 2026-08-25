import { AppEmptyState } from "./BrandElements";
import { ShioriMark } from "./Shiori";
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
// TodayStamps -- Phase 171. The three "오늘" numbers, unchanged data/markup
// from Phase 161's postmark tags -- only where they're mounted changed (see
// StudyLogPage: this now sits inside .stats-scene-v2-stamps, positioned over
// the V2 logbook photo's own three blank label shapes, instead of under a
// title/subtitle header row on a flat CSS page).
// ---------------------------------------------------------------------------
function TodayStamps({
  dueTodayCount,
  recentCount,
  hardCount,
}: {
  dueTodayCount: number;
  recentCount: number;
  hardCount: number;
}) {
  return (
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
      moodSize="md"
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
// StudyLogPage -- Phase 171 (Study Logbook V2 scene). Phase 161 already
// unboxed every section onto one flat CSS page (.stats-logbook-page, a
// plain bordered var(--paper-bg) rectangle); this phase replaces that flat
// page with a real photographed V2 logbook scene (.stats-scene-v2-frame)
// and positions the exact same content Phase 161 built -- TodayStamps,
// StudyTimeline, DeckProgressJournal, WordSlip -- directly over the photo's
// own blank stamp labels / ruled ledger table / pinned note slips. All
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
      {/* Phase 171 -- one full-bleed V2 logbook photo (a two-page desktop
          spread, a single tall page on mobile -- a different shot per
          breakpoint, not one crop of the other) is the scene anchor. The
          photo's own blank label shapes/ruled table/pinned note slips are
          never redrawn in CSS -- .stats-scene-v2-stamps/-journal/-slips
          just position the exact same TodayStamps/StudyTimeline/
          DeckProgressJournal/WordSlip markup Phase 161 already built,
          directly over those zones. See globals.css for the exact
          percentages, tuned per breakpoint against where each photo
          actually has stamp/ledger/slip room.
          Phase 173 -- the "학습 통계 / 학습 기록" eyebrow (mark + text +
          a second ShioriStamp label) used to be its own row above this
          scene. Now one compact paper tag hanging off the logbook's top
          edge instead -- see .stats-scene-v2-eyebrow, moved inside
          .stats-scene-v2-frame and absolutely positioned. */}
      <div className="stats-scene-v2">
        <div className="stats-scene-v2-frame">
          <picture className="stats-scene-v2-media">
            <source
              media="(min-width: 1024px)"
              srcSet="/brand/decor/v2/v2-stats-logbook-desktop-16x9.webp"
            />
            <img
              className="stats-scene-v2-media-img"
              src="/brand/decor/v2/v2-stats-logbook-mobile-9x16.webp"
              alt=""
              draggable={false}
            />
          </picture>

          <span className="stats-scene-v2-eyebrow">
            <ShioriMark variant="success" />
            학습 기록
          </span>

          {hasStats ? (
            <button
              type="button"
              className="stats-scene-v2-action"
              onClick={onGoToVocab}
            >
              <CardFileIcon className="button-icon" />
              어휘 노트
            </button>
          ) : null}

          {hasStats && stats ? (
            <div className="stats-scene-v2-stamps">
              <TodayStamps
                dueTodayCount={stats.due_today_count}
                recentCount={recentWords.length}
                hardCount={hardWords.length}
              />
            </div>
          ) : null}

          <div className="stats-scene-v2-journal">
            {isStatsLoading && !stats ? (
              <p className="muted-text">학습 기록을 불러오는 중입니다.</p>
            ) : null}
            {statsMessage ? <p className="message message--info">{statsMessage}</p> : null}

            {isEmpty ? <StudyLogEmptyState onGoToReading={onGoToReading} /> : null}

            {hasStats && stats ? (
              <>
                <StudyTimeline entries={journalEntries} />
                <DeckProgressJournal deckStats={stats.deck_stats} />
              </>
            ) : null}
          </div>

          {hasStats ? (
            <div className="stats-scene-v2-slips">
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
          ) : null}
        </div>
      </div>

      <footer className="stats-scene-v2-footer">
        <p className="stats-scene-v2-footer-line">
          <ShieldIcon className="info-strip-icon" />
          원문 전체는 저장하지 않아요. 단어와 짧은 예문만 노트에 남아요.
        </p>
        <p className="stats-scene-v2-footer-line">
          <BookIcon className="info-strip-icon" />
          사전 뜻풀이는 JMdict/EDRDG, Kaikki/Wiktionary 데이터를 참고합니다.
        </p>
      </footer>
    </section>
  );
}
