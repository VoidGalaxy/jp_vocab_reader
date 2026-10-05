import { useEffect, useRef, useState, type KeyboardEvent, type RefObject } from "react";
import { getDisplayMeaning } from "./shared";
import { ChevronRightIcon } from "./icons";
import type {
  DeckStats,
  ReviewLevelCount,
  StudyHistoryDay,
  StudyHistoryMonth,
  StudyStats,
  VocabItem,
} from "./types";

type StudyLogPageProps = {
  stats: StudyStats | null;
  isStatsLoading: boolean;
  statsMessage: string;
  recentWords: VocabItem[];
  hardWords: VocabItem[];
  isWordsLoading: boolean;
  onGoToVocab: () => void;
  onGoToReading: () => void;
  loadHistoryMonth: (month: string) => Promise<StudyHistoryMonth>;
  loadHistoryDay: (date: string) => Promise<StudyHistoryDay>;
};

type RegisterView = "record" | "vocab";

// ---------------------------------------------------------------------------
// Date-by-date history (GET /stats/history, /stats/history/day). Dates are
// Asia/Seoul calendar days on both sides, never the browser's own zone.
// ---------------------------------------------------------------------------
type LoadState<T> =
  | { status: "loading"; key: string }
  | { status: "error"; key: string }
  | { status: "ready"; key: string; data: T };

const SEOUL_DATE_PARTS = new Intl.DateTimeFormat("en-US", {
  timeZone: "Asia/Seoul",
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
});
const DAY_MS = 24 * 60 * 60 * 1000;
const SEOUL_OFFSET_MS = 9 * 60 * 60 * 1000; // no DST in Seoul since 1988

function seoulTodayKey(now = new Date()) {
  const parts = Object.fromEntries(
    SEOUL_DATE_PARTS.formatToParts(now).map((part) => [part.type, part.value]),
  );
  return `${parts.year}-${parts.month}-${parts.day}`;
}

function msUntilNextSeoulMidnight(now = Date.now()) {
  return DAY_MS - ((now + SEOUL_OFFSET_MS) % DAY_MS) + 1000;
}

// The Seoul calendar date, refreshed at Seoul midnight and whenever the tab
// becomes visible again (timers can be paused while a laptop sleeps).
function useSeoulToday() {
  const [todayKey, setTodayKey] = useState(() => seoulTodayKey());
  useEffect(() => {
    let timer = 0;
    const refresh = () => setTodayKey(seoulTodayKey());
    const schedule = () => {
      timer = window.setTimeout(() => {
        refresh();
        schedule();
      }, msUntilNextSeoulMidnight());
    };
    const onVisible = () => {
      if (document.visibilityState === "visible") {
        refresh();
      }
    };
    schedule();
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      window.clearTimeout(timer);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, []);
  return todayKey;
}

const WEEKDAYS = ["일", "월", "화", "수", "목", "금", "토"];

function pad2(value: number) {
  return String(value).padStart(2, "0");
}

function toDateKey(date: Date) {
  return `${date.getFullYear()}-${pad2(date.getMonth() + 1)}-${pad2(date.getDate())}`;
}

function fromDateKey(key: string) {
  const [year, month, day] = key.split("-").map(Number);
  return new Date(year, month - 1, day);
}

function toMonthKey(year: number, month: number) {
  return `${year}-${pad2(month + 1)}`;
}

function formatDayName(key: string) {
  const date = fromDateKey(key);
  return `${date.getMonth() + 1}월 ${date.getDate()}일 ${WEEKDAYS[date.getDay()]}요일`;
}

function formatShortDate(key: string) {
  const date = fromDateKey(key);
  return `${pad2(date.getMonth() + 1)}.${pad2(date.getDate())}`;
}

function formatCount(value: number) {
  return value.toLocaleString("ko-KR");
}

function toPercent(rate: number) {
  return Math.round(rate * 100);
}

// ---------------------------------------------------------------------------
// Register header: title, the two inner tabs (roving tabindex, arrow keys),
// and the static scope label.
// ---------------------------------------------------------------------------
function RegisterTabs({
  view,
  onChange,
}: {
  view: RegisterView;
  onChange: (next: RegisterView) => void;
}) {
  const recordRef = useRef<HTMLButtonElement>(null);
  const vocabRef = useRef<HTMLButtonElement>(null);

  function select(next: RegisterView) {
    onChange(next);
    (next === "record" ? recordRef : vocabRef).current?.focus({ preventScroll: true });
  }

  function handleKeyDown(event: KeyboardEvent<HTMLButtonElement>) {
    if (event.key === "ArrowLeft" || event.key === "ArrowRight") {
      event.preventDefault();
      select(view === "record" ? "vocab" : "record");
    } else if (event.key === "Home") {
      event.preventDefault();
      select("record");
    } else if (event.key === "End") {
      event.preventDefault();
      select("vocab");
    }
  }

  return (
    <div className="stats-reg-tabs" role="tablist" aria-label="통계 화면">
      <button
        ref={recordRef}
        type="button"
        role="tab"
        id="stats-reg-tab-record"
        aria-selected={view === "record"}
        aria-controls="stats-reg-panel"
        tabIndex={view === "record" ? 0 : -1}
        onClick={() => onChange("record")}
        onKeyDown={handleKeyDown}
      >
        학습 기록
      </button>
      <button
        ref={vocabRef}
        type="button"
        role="tab"
        id="stats-reg-tab-vocab"
        aria-selected={view === "vocab"}
        aria-controls="stats-reg-panel"
        tabIndex={view === "vocab" ? 0 : -1}
        onClick={() => onChange("vocab")}
        onKeyDown={handleKeyDown}
      >
        어휘 현황
      </button>
    </div>
  );
}

// ---------------------------------------------------------------------------
// 학습 기록 -- left page: month controls, calendar, month summary.
// ---------------------------------------------------------------------------
function CalendarPage({
  year,
  month,
  todayKey,
  selectedKey,
  monthState,
  onMonthChange,
  onSelect,
  onRetry,
  onCalendarKeyDown,
  calendarRef,
}: {
  year: number;
  month: number;
  todayKey: string;
  selectedKey: string;
  monthState: LoadState<StudyHistoryMonth>;
  onMonthChange: (delta: number) => void;
  onSelect: (key: string) => void;
  onRetry: () => void;
  onCalendarKeyDown: (event: KeyboardEvent<HTMLDivElement>) => void;
  calendarRef: RefObject<HTMLDivElement>;
}) {
  const history = monthState.status === "ready" ? monthState.data : null;
  const today = fromDateKey(todayKey);
  const isCurrentMonth = year === today.getFullYear() && month === today.getMonth();
  const first = new Date(year, month, 1);
  const offset = first.getDay();
  const daysInMonth = new Date(year, month + 1, 0).getDate();
  const cellCount = Math.ceil((offset + daysInMonth) / 7) * 7;
  const dayMap = new Map((history?.days ?? []).map((day) => [day.date, day]));

  const cells = Array.from({ length: cellCount }, (_, index) => {
    const date = new Date(year, month, 1 - offset + index);
    const key = toDateKey(date);
    const inside = date.getMonth() === month;
    const future = key > todayKey;
    const record = dayMap.get(key);
    const reviews = record?.review_count ?? 0;
    const selectable = inside && !future;
    let label = formatDayName(key);
    if (future) {
      label += " 아직 기록 없음";
    } else if (record) {
      label += ` 복습 ${reviews}회, 담은 단어 ${record?.saved_word_count ?? 0}개`;
    }

    return (
      <button
        key={key}
        type="button"
        className={[
          "stats-reg-day",
          inside ? "" : "is-outside",
          future ? "is-future" : "",
          key === selectedKey && inside ? "is-selected" : "",
          key === todayKey ? "is-today" : "",
        ]
          .filter(Boolean)
          .join(" ")}
        aria-pressed={key === selectedKey && inside}
        data-date={key}
        tabIndex={key === selectedKey && inside ? 0 : -1}
        aria-label={label}
        disabled={!selectable}
        onClick={() => onSelect(key)}
      >
        <span className="stats-reg-day-num">{date.getDate()}</span>
        {selectable && record ? (
          <>
            <span className="stats-reg-day-count">
              {reviews ? (
                <>
                  {reviews}
                  <small>회</small>
                </>
              ) : (
                "—"
              )}
            </span>
            <i className={`stats-reg-day-mark${reviews ? " is-active" : ""}`} />
          </>
        ) : null}
      </button>
    );
  });

  return (
    <section className="stats-reg-page stats-reg-calendar-page" aria-label="월간 달력">
      <div className="stats-reg-month-controls">
        <button
          type="button"
          className="stats-reg-icon-button is-prev"
          aria-label="이전 달"
          title="이전 달"
          onClick={() => onMonthChange(-1)}
        >
          <ChevronRightIcon />
        </button>
        <strong aria-live="polite">
          {year}년 {month + 1}월
        </strong>
        <button
          type="button"
          className="stats-reg-icon-button"
          aria-label="다음 달"
          title="다음 달"
          disabled={isCurrentMonth}
          onClick={() => onMonthChange(1)}
        >
          <ChevronRightIcon />
        </button>
      </div>

      <div className="stats-reg-calendar">
        <div className="stats-reg-weekdays" aria-hidden="true">
          {WEEKDAYS.map((name) => (
            <span key={name}>{name}</span>
          ))}
        </div>
        <div
          ref={calendarRef}
          className="stats-reg-days"
          role="group"
          aria-label="날짜 선택. 화살표로 날짜, Page Up과 Page Down으로 달을 옮겨요."
          onKeyDown={onCalendarKeyDown}
        >
          {cells}
        </div>
      </div>

      <div className="stats-reg-month-summary">
        <p>{month + 1}월의 성과</p>
        {history ? (
          <div>
            <span>
              복습
              <strong>
                {formatCount(history.summary.review_count)}
                <small>회</small>
              </strong>
            </span>
            <span>
              담은 단어
              <strong>
                {formatCount(history.summary.saved_word_count)}
                <small>개</small>
              </strong>
            </span>
            <span>
              학습한 날
              <strong>
                {history.summary.active_days}
                <small>일</small>
              </strong>
            </span>
          </div>
        ) : monthState.status === "error" ? (
          <p className="stats-reg-pending">
            이달 기록을 불러오지 못했어요.{" "}
            <button type="button" className="stats-reg-text-link" onClick={onRetry}>
              다시 시도
            </button>
          </p>
        ) : (
          <p className="stats-reg-pending stats-reg-quiet">기록을 불러오는 중이에요.</p>
        )}
      </div>
    </section>
  );
}

// ---------------------------------------------------------------------------
// 학습 기록 -- right page: the selected day.
// ---------------------------------------------------------------------------
const RATING_ROWS = [
  ["다시", "again"],
  ["어려움", "hard"],
  ["보통", "good"],
  ["쉬움", "easy"],
] as const;

function DayPage({
  selectedKey,
  todayKey,
  monthState,
  dayState,
  onRetryMonth,
  onRetryDay,
}: {
  selectedKey: string;
  todayKey: string;
  monthState: LoadState<StudyHistoryMonth>;
  dayState: LoadState<StudyHistoryDay> | null;
  onRetryMonth: () => void;
  onRetryDay: () => void;
}) {
  const month = monthState.status === "ready" ? monthState.data : null;
  const record = month?.days.find((day) => day.date === selectedKey) ?? null;
  const reviews = record?.review_count ?? 0;
  const saved = record?.saved_word_count ?? 0;
  const streak = month?.current_streak ?? null;

  let body;
  if (monthState.status === "loading") {
    body = <p className="stats-reg-quiet stats-reg-day-status">기록을 불러오는 중이에요.</p>;
  } else if (monthState.status === "error" || !record) {
    // A failed lookup is never shown as a day with no activity.
    body = (
      <div className="stats-reg-unlinked">
        <p className="stats-reg-unlinked-title">이 날짜의 기록을 불러오지 못했어요.</p>
        <button type="button" className="stats-reg-text-link" onClick={onRetryMonth}>
          다시 시도
        </button>
      </div>
    );
  } else if (reviews || saved) {
    body = (
      <>
        <div className="stats-reg-daily-numbers">
          <span>
            복습
            <strong>
              {formatCount(reviews)}
              <small>회</small>
            </strong>
          </span>
          <span>
            새로 담은 단어
            <strong>
              {formatCount(saved)}
              <small>개</small>
            </strong>
          </span>
        </div>
        <div className="stats-reg-ratings">
          {RATING_ROWS.map(([name, key], index) => (
            <div className={`stats-reg-rating is-r${index}`} key={key}>
              <span>{name}</span>
              <strong>
                {formatCount(record.ratings[key])}
                <small>회</small>
              </strong>
            </div>
          ))}
        </div>
        <section className="stats-reg-dated-words">
          <h3>
            이날 담은 단어
            <small>지금 노트에 남아 있는 내 단어 기준</small>
          </h3>
          {saved === 0 ? (
            <p className="stats-reg-quiet">새로 담은 단어가 없습니다.</p>
          ) : !dayState || dayState.status === "loading" ? (
            <p className="stats-reg-quiet">단어를 불러오는 중이에요.</p>
          ) : dayState.status === "error" ? (
            <p className="stats-reg-quiet">
              단어 목록을 불러오지 못했어요.{" "}
              <button type="button" className="stats-reg-text-link" onClick={onRetryDay}>
                다시 시도
              </button>
            </p>
          ) : (
            <>
              {dayState.data.saved_words.slice(0, 3).map((word) => (
                <div className="stats-reg-word" key={word.id}>
                  <span>
                    <b lang="ja">{word.surface}</b>
                    {word.reading && word.reading !== word.surface ? (
                      <small lang="ja">{word.reading}</small>
                    ) : null}
                  </span>
                  <span>{getDisplayMeaning(word.meaning_ko)}</span>
                </div>
              ))}
              {dayState.data.saved_word_count > 3 ? (
                <p className="stats-reg-quiet">
                  외 {formatCount(dayState.data.saved_word_count - 3)}개
                </p>
              ) : null}
            </>
          )}
        </section>
      </>
    );
  } else {
    body = (
      <div className="stats-reg-rest">
        <span aria-hidden="true">—</span>
        <h3>쉬어간 날</h3>
        <p>이날은 복습 기록이 없습니다.</p>
      </div>
    );
  }

  return (
    <section className="stats-reg-page stats-reg-day-page" aria-label="선택한 날">
      <div className="stats-reg-day-heading">
        <p className="stats-reg-eyebrow">{selectedKey === todayKey ? "오늘" : "선택한 날"}</p>
        <h2>{formatDayName(selectedKey)}</h2>
      </div>

      {body}

      {streak ? (
        <div className="stats-reg-streak" title={streak.definition}>
          <span>현재 연속 학습</span>
          <strong>
            {formatCount(streak.days)}
            <small>{streak.capped ? "일 이상" : "일"}</small>
          </strong>
          {streak.starts_on && streak.ends_on ? (
            <span>
              {formatShortDate(streak.starts_on)} – {formatShortDate(streak.ends_on)}
            </span>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}

// ---------------------------------------------------------------------------
// 어휘 현황 -- left page: current classification + per-deck mastery. Both are
// the existing personal-vocab /stats aggregates; nothing is added to them.
// ---------------------------------------------------------------------------
const STATUS_ROWS = [
  { key: "known_count", label: "아는 단어", tone: "known" },
  { key: "uncertain_count", label: "헷갈리는 단어", tone: "uncertain" },
  { key: "unknown_count", label: "모르는 단어", tone: "unknown" },
  { key: "unclassified_count", label: "미분류", tone: "unclassified" },
] as const;

function InventoryPage({
  stats,
  onGoToReading,
}: {
  stats: StudyStats;
  onGoToReading: () => void;
}) {
  const counts = STATUS_ROWS.map((row) => stats[row.key]);
  const total = stats.total_count;

  return (
    <section className="stats-reg-page stats-reg-inventory-page" aria-label="단어 분류">
      <div className="stats-reg-total">
        <span>모아 둔 단어</span>
        <strong>
          {formatCount(total)}
          <small>개</small>
        </strong>
        <span className="stats-reg-learned">아는 단어 {toPercent(stats.learned_rate)}%</span>
        {/* /stats due_today_count is personal + subscribed decks; not a
            date-by-date figure, so it stays with the current inventory. */}
        <span className="stats-reg-due">
          오늘 복습 예정 <b>{formatCount(stats.due_today_count)}</b>개
          <small>구독 덱 포함</small>
        </span>
      </div>
      <div
        className="stats-reg-composition"
        role="img"
        aria-label={STATUS_ROWS.map((row, i) => `${row.label} ${counts[i]}개`).join(", ")}
      >
        {total > 0
          ? STATUS_ROWS.map((row, i) =>
              counts[i] > 0 ? (
                <span key={row.key} className={`is-${row.tone}`} style={{ flexGrow: counts[i] }} />
              ) : null,
            )
          : null}
      </div>
      <div className="stats-reg-four">
        {STATUS_ROWS.map((row, i) => (
          <div key={row.key}>
            <span>
              <i className={`stats-reg-dot is-${row.tone}`} />
              {row.label}
            </span>
            <strong>{formatCount(counts[i])}</strong>
          </div>
        ))}
      </div>

      {total === 0 ? (
        <p className="stats-reg-quiet stats-reg-empty-line">
          아직 담은 단어가 없어요.{" "}
          <button type="button" className="stats-reg-text-link" onClick={onGoToReading}>
            원문 읽기 시작
          </button>
        </p>
      ) : null}

      <DeckMastery deckStats={stats.deck_stats} />
    </section>
  );
}

// The old logbook's "최근 담은 단어" -- most recently saved words, not a
// date-by-date record -- kept as a small footer disclosure.
function RecentWordsNotice({
  recentWords,
  isWordsLoading,
}: {
  recentWords: VocabItem[];
  isWordsLoading: boolean;
}) {
  return (
    <details className="stats-reg-notice stats-reg-recent">
      <summary>최근 담은 단어</summary>
      <div>
        {isWordsLoading && recentWords.length === 0 ? (
          <p className="stats-reg-quiet">불러오는 중...</p>
        ) : recentWords.length === 0 ? (
          <p className="stats-reg-quiet">아직 담은 단어가 없어요.</p>
        ) : (
          <ul>
            {recentWords.map((item) => (
              <li key={item.id}>
                <b lang="ja">{item.surface}</b>
                {item.reading && item.reading !== item.surface ? (
                  <small lang="ja">{item.reading}</small>
                ) : null}
                <span>{getDisplayMeaning(item.meaning_ko)}</span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </details>
  );
}

function DeckMastery({ deckStats }: { deckStats: DeckStats[] }) {
  return (
    <section className="stats-reg-section stats-reg-decks">
      <h2>단어장별 익힘</h2>
      {deckStats.length === 0 ? (
        <p className="stats-reg-quiet">아직 단어장이 없어요.</p>
      ) : (
        deckStats.map((deck) => (
          <div className="stats-reg-deck" key={deck.deck_id}>
            <div>
              <strong>{deck.deck_name}</strong>
              <b>{toPercent(deck.learned_rate)}%</b>
            </div>
            <div className="stats-reg-meter">
              <i style={{ width: `${deck.learned_rate * 100}%` }} />
            </div>
            <p>
              <span>
                {formatCount(deck.known_count)} / {formatCount(deck.total_count)}개 아는 단어
              </span>
              <span>오늘 복습 {formatCount(deck.due_today_count)}개</span>
            </p>
          </div>
        ))
      )}
    </section>
  );
}

// ---------------------------------------------------------------------------
// 어휘 현황 -- right page: review stages, lifetime results, often-missed words.
// ---------------------------------------------------------------------------
function ReviewPage({
  stats,
  hardWords,
  isWordsLoading,
}: {
  stats: StudyStats;
  hardWords: VocabItem[];
  isWordsLoading: boolean;
}) {
  return (
    <section className="stats-reg-page stats-reg-review-page" aria-label="복습 현황">
      <StageBars levels={stats.review_level_counts} />

      <section className="stats-reg-section stats-reg-lifetime">
        <h2>누적 복습</h2>
        <div>
          <span>
            맞음
            <strong>
              {formatCount(stats.total_correct_count)}
              <small>회</small>
            </strong>
          </span>
          <span>
            틀림
            <strong>
              {formatCount(stats.total_wrong_count)}
              <small>회</small>
            </strong>
          </span>
          <span>
            평균 단계
            <strong>{stats.average_review_level.toFixed(1)}</strong>
          </span>
        </div>
      </section>

      <section className="stats-reg-section stats-reg-missed">
        <h2>자주 틀린 단어</h2>
        {isWordsLoading && hardWords.length === 0 ? (
          <p className="stats-reg-quiet">불러오는 중...</p>
        ) : hardWords.length === 0 ? (
          <p className="stats-reg-quiet">아직 자주 틀린 단어가 없어요.</p>
        ) : (
          hardWords.slice(0, 3).map((item) => (
            <div className="stats-reg-missed-row" key={item.id}>
              <span>
                <b lang="ja">{item.surface}</b>
                {item.reading && item.reading !== item.surface ? (
                  <small lang="ja">{item.reading}</small>
                ) : null}
              </span>
              <span>{getDisplayMeaning(item.meaning_ko)}</span>
              <em>{formatCount(item.wrong_count)}회 틀림</em>
            </div>
          ))
        )}
      </section>
    </section>
  );
}

function StageBars({ levels }: { levels: ReviewLevelCount[] }) {
  const sorted = [...levels].sort((a, b) => a.review_level - b.review_level);
  const max = Math.max(1, ...sorted.map((level) => level.count));
  return (
    <section className="stats-reg-section stats-reg-stages">
      <h2>복습 단계</h2>
      {sorted.length === 0 ? (
        <p className="stats-reg-quiet">아직 복습 단계 정보가 없어요.</p>
      ) : (
        <div
          className="stats-reg-stage-bars"
          role="img"
          aria-label={sorted.map((l) => `${l.review_level}단계 ${l.count}개`).join(", ")}
        >
          {sorted.map((level) => (
            <div key={level.review_level}>
              <span>{level.review_level}단계</span>
              <i>
                <b style={{ width: `${(level.count / max) * 100}%` }} />
              </i>
              <strong>{formatCount(level.count)}</strong>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}

// ---------------------------------------------------------------------------
// StudyLogPage -- Stats A "two-page register". One quiet bound record book
// with two inner views: 학습 기록 (calendar + selected day) and 어휘 현황
// (current /stats aggregates). Replaces the old V2 logbook photo with
// absolutely positioned stamps/notes. Phones and tablets stack both pages
// into one continuous sheet. Approved reference:
// references/mockups/stats-two-view-three/handoff/approved/a-*.png
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
  loadHistoryMonth,
  loadHistoryDay,
}: StudyLogPageProps) {
  const [view, setView] = useState<RegisterView>("record");
  const todayKey = useSeoulToday();
  const [cursor, setCursor] = useState(() => {
    const today = fromDateKey(todayKey);
    return { year: today.getFullYear(), month: today.getMonth() };
  });
  const [selectedKey, setSelectedKey] = useState(todayKey);
  const [reloadToken, setReloadToken] = useState(0);
  const monthKey = toMonthKey(cursor.year, cursor.month);
  const [monthState, setMonthState] = useState<LoadState<StudyHistoryMonth>>({
    status: "loading",
    key: monthKey,
  });
  const [dayState, setDayState] = useState<LoadState<StudyHistoryDay> | null>(null);

  // page.tsx passes fresh closures every render; keep the latest in refs so
  // they never re-trigger the fetch effects below.
  const loadersRef = useRef({ loadHistoryMonth, loadHistoryDay });
  loadersRef.current = { loadHistoryMonth, loadHistoryDay };

  // Seoul midnight: today's cell, the selected "오늘" and the current month
  // move forward together, and the visible month is fetched again.
  const selectedKeyRef = useRef(selectedKey);
  selectedKeyRef.current = selectedKey;
  const previousTodayRef = useRef(todayKey);
  useEffect(() => {
    const previous = previousTodayRef.current;
    if (previous === todayKey) {
      return;
    }
    previousTodayRef.current = todayKey;
    if (selectedKeyRef.current === previous) {
      const today = fromDateKey(todayKey);
      setSelectedKey(todayKey);
      setCursor({ year: today.getFullYear(), month: today.getMonth() });
    }
    setReloadToken((token) => token + 1);
  }, [todayKey]);

  // Month: only the latest request may land (fast month switching).
  useEffect(() => {
    let active = true;
    setMonthState({ status: "loading", key: monthKey });
    loadersRef.current
      .loadHistoryMonth(monthKey)
      .then((data) => {
        if (active) {
          setMonthState({ status: "ready", key: monthKey, data });
        }
      })
      .catch(() => {
        if (active) {
          setMonthState({ status: "error", key: monthKey });
        }
      });
    return () => {
      active = false;
    };
  }, [monthKey, reloadToken]);

  // Selected day's saved-word list, only when that day has any.
  const monthData =
    monthState.status === "ready" && monthState.key === monthKey ? monthState.data : null;
  const selectedSavedCount =
    monthData?.days.find((day) => day.date === selectedKey)?.saved_word_count ?? 0;
  const [dayReloadToken, setDayReloadToken] = useState(0);
  useEffect(() => {
    if (!monthData || selectedSavedCount === 0) {
      setDayState(null);
      return;
    }
    let active = true;
    setDayState({ status: "loading", key: selectedKey });
    loadersRef.current
      .loadHistoryDay(selectedKey)
      .then((data) => {
        if (active) {
          setDayState({ status: "ready", key: selectedKey, data });
        }
      })
      .catch(() => {
        if (active) {
          setDayState({ status: "error", key: selectedKey });
        }
      });
    return () => {
      active = false;
    };
  }, [monthData, selectedKey, selectedSavedCount, dayReloadToken]);

  const visibleMonthState: LoadState<StudyHistoryMonth> =
    monthState.key === monthKey ? monthState : { status: "loading", key: monthKey };
  const visibleDayState = dayState && dayState.key === selectedKey ? dayState : null;

  // Calendar keyboard: one Tab stop (the selected day); arrows move the
  // selection by a day/week, Home/End to the week's ends, PageUp/PageDown by
  // a month. Crossing into another month moves the calendar with it. Future
  // days are skipped (selection stops at today).
  const [focusRequest, setFocusRequest] = useState(0);
  function moveSelection(target: string) {
    const clamped = target > todayKey ? todayKey : target;
    if (clamped === selectedKey) {
      return;
    }
    const date = fromDateKey(clamped);
    if (date.getFullYear() !== cursor.year || date.getMonth() !== cursor.month) {
      setCursor({ year: date.getFullYear(), month: date.getMonth() });
    }
    setSelectedKey(clamped);
    setFocusRequest((n) => n + 1);
  }

  function handleCalendarKey(event: KeyboardEvent<HTMLDivElement>) {
    const current = fromDateKey(selectedKey);
    let target: Date | null = null;
    switch (event.key) {
      case "ArrowLeft":
        target = new Date(current.getFullYear(), current.getMonth(), current.getDate() - 1);
        break;
      case "ArrowRight":
        target = new Date(current.getFullYear(), current.getMonth(), current.getDate() + 1);
        break;
      case "ArrowUp":
        target = new Date(current.getFullYear(), current.getMonth(), current.getDate() - 7);
        break;
      case "ArrowDown":
        target = new Date(current.getFullYear(), current.getMonth(), current.getDate() + 7);
        break;
      case "Home":
        target = new Date(current.getFullYear(), current.getMonth(), current.getDate() - current.getDay());
        break;
      case "End":
        target = new Date(current.getFullYear(), current.getMonth(), current.getDate() + 6 - current.getDay());
        break;
      case "PageUp":
      case "PageDown": {
        const delta = event.key === "PageUp" ? -1 : 1;
        const lastDay = new Date(current.getFullYear(), current.getMonth() + delta + 1, 0).getDate();
        target = new Date(
          current.getFullYear(),
          current.getMonth() + delta,
          Math.min(current.getDate(), lastDay),
        );
        break;
      }
      default:
        return;
    }
    event.preventDefault();
    moveSelection(toDateKey(target));
  }

  const calendarRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (focusRequest === 0) {
      return;
    }
    calendarRef.current
      ?.querySelector<HTMLButtonElement>(`[data-date="${selectedKey}"]`)
      ?.focus({ preventScroll: true });
  }, [focusRequest, selectedKey, cursor]);

  function changeMonth(delta: number) {
    const next = new Date(cursor.year, cursor.month + delta, 1);
    const year = next.getFullYear();
    const month = next.getMonth();
    setCursor({ year, month });
    const today = fromDateKey(todayKey);
    if (year === today.getFullYear() && month === today.getMonth()) {
      setSelectedKey(todayKey);
    } else {
      setSelectedKey(toDateKey(new Date(year, month + 1, 0)));
    }
  }

  let vocabBody = null;
  if (stats) {
    vocabBody = (
      <>
        <InventoryPage stats={stats} onGoToReading={onGoToReading} />
        <ReviewPage stats={stats} hardWords={hardWords} isWordsLoading={isWordsLoading} />
      </>
    );
  } else {
    vocabBody = (
      <section className="stats-reg-page stats-reg-status-page">
        {isStatsLoading ? (
          <p className="stats-reg-quiet">어휘 현황을 불러오는 중입니다.</p>
        ) : statsMessage ? (
          <p className="stats-reg-error" role="alert">
            {statsMessage}
          </p>
        ) : (
          <p className="stats-reg-quiet">
            아직 기록이 없어요.{" "}
            <button type="button" className="stats-reg-text-link" onClick={onGoToReading}>
              원문 읽기 시작
            </button>
          </p>
        )}
      </section>
    );
  }

  return (
    <section className="tab-panel stats-register">
      <div className="stats-reg-book">
        <header className="stats-reg-head">
          <div className="stats-reg-title">
            <p className="stats-reg-eyebrow">나의 일본어</p>
            <h1>학습 통계</h1>
          </div>
          <RegisterTabs view={view} onChange={setView} />
          <span className="stats-reg-scope">전체 단어장</span>
        </header>

        <div
          id="stats-reg-panel"
          role="tabpanel"
          aria-labelledby={`stats-reg-tab-${view}`}
          className={`stats-reg-body is-${view}`}
        >
          {view === "record" ? (
            <>
              <CalendarPage
                year={cursor.year}
                month={cursor.month}
                todayKey={todayKey}
                selectedKey={selectedKey}
                monthState={visibleMonthState}
                onMonthChange={changeMonth}
                onSelect={setSelectedKey}
                onCalendarKeyDown={handleCalendarKey}
                calendarRef={calendarRef}
                onRetry={() => setReloadToken((token) => token + 1)}
              />
              <DayPage
                selectedKey={selectedKey}
                todayKey={todayKey}
                monthState={visibleMonthState}
                dayState={visibleDayState}
                onRetryMonth={() => setReloadToken((token) => token + 1)}
                onRetryDay={() => setDayReloadToken((token) => token + 1)}
              />
            </>
          ) : (
            vocabBody
          )}
        </div>

        <footer className="stats-reg-foot">
          {stats && statsMessage ? (
            // A failed refresh keeps the last loaded numbers on the page but
            // must still say so.
            <p className="stats-reg-refresh-error" role="alert">
              {statsMessage} 마지막으로 불러온 어휘 현황을 보여 드리고 있어요.
            </p>
          ) : (
            <span>
              {view === "record"
                ? "서울 시간 기준 · 복습은 구독 덱 포함"
                : "전체 어휘 현황"}
            </span>
          )}
          <span className="stats-reg-foot-links">
            <RecentWordsNotice recentWords={recentWords} isWordsLoading={isWordsLoading} />
            <button type="button" className="stats-reg-text-link" onClick={onGoToVocab}>
              어휘 노트
            </button>
            <details className="stats-reg-notice">
              <summary>개인정보·출처</summary>
              <div>
                <p>원문 전체는 저장하지 않아요. 단어와 짧은 예문만 노트에 남아요.</p>
                <p>사전 뜻풀이는 JMdict/EDRDG, Kaikki/Wiktionary 데이터를 참고합니다.</p>
              </div>
            </details>
          </span>
        </footer>
      </div>
    </section>
  );
}
