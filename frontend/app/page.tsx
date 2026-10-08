"use client";

import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import { AccountMenu } from "../components/AccountMenu";
import { AppShell, type NavAction } from "../components/AppShell";
import { GlobalFeedbackModal } from "../components/GlobalFeedbackModal";
import {
  getTokenGroupKey,
  getTokenStatus,
  isTokenSavedInDeck,
  resolveSelectedReadingSaveTargets,
} from "../components/coverageUtils";
import type { ReadingSaveTarget } from "../components/coverageUtils";
import { HomeDashboard } from "../components/HomeDashboard";
import {
  LearningPlanPanel,
  type PlanDraftMemory,
  type PlanDraftMemoryEntry,
} from "../components/LearningPlanPanel";
import { LegacyClassificationDraftNotice } from "../components/LegacyClassificationDraftNotice";
import { learningPlanStorageScope } from "../components/learningPlanStorage";
import {
  LEGACY_READING_SESSION_KEY,
  copyToEmptyReadingSession,
  detachServerLinks,
  originalTextDownload,
  rawBackupDownload,
  readLegacyReadingSession,
  readLegacyReadingSessionRaw,
  readReadingSession,
  readingSessionKey,
  readingStorageCapability,
  removeReadingSession,
  saveReadingSession,
  type ReadingDownload,
  type ReadingOwner,
  type ReadingSessionData,
  type ReadingSessionVersion,
  type ReadingStorageEnv,
  type SaveResult,
} from "../components/readingSessionStorage";
import {
  captureReadingContext as captureReadingContextFrom,
  createRequestSequence,
  recheckAfterUnverified,
  requiresDeckConfirmation,
  type LastStorageAttempt,
} from "../components/readingSessionFlow";
import {
  ReadingAccountGate,
  ReadingStorageNotice,
  ReadingSwitchDialog,
  type ReadingRecoveryOffer,
  type ReadingStorageStatus,
} from "../components/ReadingStorageNotice";
import {
  BookIcon,
  BookshelfIcon,
  CardFileIcon,
  CardsIcon,
  ChatIcon,
  ClockIcon,
  HomeIcon,
  PencilIcon,
} from "../components/icons";
import { StudyLogPage } from "../components/InfoSection";
import { MeaningFeedbackModal } from "../components/MeaningFeedbackModal";
import {
  createPlanStudyLauncher,
  type PlanStudyLauncher,
  type PlanStudyTarget,
  type StudySessionSnapshot,
} from "../components/planStudyLauncher";
import { runAccountScopedRefresh } from "../components/accountScopedRefresh";
import {
  analyzeLongTextInChunks,
  type ChunkAnalyzeProgress,
} from "../components/readingChunkAnalyze";
import { ReadingTab, SAMPLE_TEXT } from "../components/ReadingTab";
import { SharedDeckSection } from "../components/SharedDeckSection";
import { buildRatingFeedbackMessage, withObjectParticle } from "../components/shared";
import { splitTextIntoChunks } from "../components/textChunking";
import { StudySection } from "../components/StudySection";
import { VocabSection } from "../components/VocabSection";
import type {
  ReviewResult,
  AppFeedbackCategory,
  Deck,
  MeaningFeedbackTarget,
  SessionReviewCounts,
  StudyMode,
  Token,
  TokenStatus,
  TokenWithStatus,
  CustomTerm,
  CustomTermFormData,
  VocabFormData,
  VocabItem,
  VocabSort,
  StudyHistoryDay,
  StudyHistoryMonth,
  StudyStats,
  StudyCardItem,
  StudyLexemeItem,
  SharedDeckDetail,
  SharedDeckSummary,
} from "../components/types";

type AnalyzeResponse = {
  tokens: Token[];
  ignored_token_count: number;
};

type VocabItemsResponse = {
  items: VocabItem[];
};

type StudyItemsResponse = {
  items: VocabItem[];
};

const SHARED_DECK_STUDY_ID_PREFIX = "shared:";

function isSharedDeckStudyId(deckId: string) {
  return deckId.startsWith(SHARED_DECK_STUDY_ID_PREFIX);
}

// Phase 20 Round 2: caps how many never-reviewed shared-deck lexemes a "새
// 단어" (new word) session pulls in at once -- subscribing to a large
// lexeme-mode deck (e.g. JLPT N1, 3,475 words) otherwise puts all of them
// in a single session. Only applied to the "new" mode fetches below; "오늘
// 복습" (today/due) and status-filtered modes are unaffected.
const NEW_LEXEME_STUDY_LIMIT = 30;

type LexemeReviewResponse = {
  lexeme_id: number;
  status: string;
  review_level: number;
  next_review_at: string | null;
  correct_count: number;
  wrong_count: number;
  last_reviewed_at: string | null;
};

type StatsResponse = StudyStats;

type DecksResponse = {
  items: Deck[];
};

type CustomTermsResponse = {
  items: CustomTerm[];
};

type DeckDeleteResponse = {
  deleted_deck_id: number;
  deleted_vocab_count: number;
  message: string;
};

type DeckPackageImportResponse = {
  deck_id: number;
  deck_name: string;
  imported_vocab_count: number;
  skipped_vocab_count: number;
  imported_custom_term_count: number;
  skipped_custom_term_count: number;
  message: string;
};

type DeckPublishResponse = {
  shared_deck_id: number;
  title: string;
  vocab_count: number;
  custom_term_count: number;
  message: string;
};

type SharedDeckImportResponse = {
  deck_id: number;
  deck_name: string;
  imported_vocab_count: number;
  imported_custom_term_count: number;
  message: string;
  // Additive -- see docs/architecture/shared-lexeme-progress-storage.md.
  // "subscribed" means this deck's words live in the shared lexeme table
  // and were NOT copied into a personal deck/vocab_items; there is no real
  // deck_id to select/load in that case.
  mode?: "copied" | "subscribed";
  subscribed?: boolean;
  word_count?: number;
};

type SharedDeckDeleteResponse = {
  ok: boolean;
  shared_deck_id: number;
  title: string;
  message: string;
};

// Phase 7 Round 5/8 -- see docs/architecture/shared-lexeme-progress-storage.md
// "Owner unpublish policy" republish decision. Same shape as the delete
// response above; it's the owner-only reversal of that same action.
type SharedDeckRepublishResponse = {
  ok: boolean;
  shared_deck_id: number;
  title: string;
  message: string;
};

// Response from PATCH/POST .../shared-decks/{id}/words/{lexeme_id}/(progress|review)
// -- see docs/architecture/shared-lexeme-progress-storage.md.
type LexemeWordProgressResponse = {
  lexeme_id: number;
  status: TokenStatus;
  review_level: number;
  next_review_at: string | null;
  correct_count: number;
  wrong_count: number;
  last_reviewed_at: string | null;
};

type CurrentUser = {
  id: number;
  email: string;
  display_name: string;
  auth_provider: string;
};

type AuthResponse = {
  access_token: string;
  token_type: "bearer";
  user: CurrentUser;
};

type TabKey =
  | "home"
  | "plan"
  | "reading"
  | "vocab"
  | "study"
  | "shared"
  | "info";
type VocabStatusFilter = "all" | TokenStatus;

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL || "http://127.0.0.1:8000";
// Old 빠른 분류 device draft. Only LegacyClassificationDraftNotice touches it,
// and only on an explicit user action (download / open text / delete).
const CLASSIFICATION_DRAFT_KEY = "jp-vocab-reader:classification-draft";
// Learning-plan device storage is scoped by backend environment + user id.
const LEARNING_PLAN_STORAGE_SCOPE = learningPlanStorageScope(API_BASE_URL);
const ACCESS_TOKEN_KEY = "jp-vocab-reader:access-token";
// Client-side only sanity check for a friendlier signup/login error message --
// the backend (see backend/app/main.py register_user) only rejects a blank
// email, so this never blocks anything the API would have accepted.
const EMAIL_FORMAT_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
// Must match the backend's actual minimum (backend/app/main.py register_user:
// `if len(request.password) < 8`) -- never invent a stricter policy here.
const AUTH_MIN_PASSWORD_LENGTH = 8;

// User-facing screen names, "조용한 서재의 학습 책상" concept -- route/state
// keys (TabKey) and every internal handler/variable stay on their original
// functional names (plan/reading/vocab/study/shared/info) on purpose, so
// this rename never touches routing or state management, only what people
// actually read. mobileLabel is a shorter form for the bottom tab bar only
// (falls back to `label` when omitted) -- the sidebar/feedback-modal screen
// label always uses the full `label`.
const tabs: Array<{
  key: TabKey;
  label: string;
  mobileLabel?: string;
  icon: (props: { className?: string }) => JSX.Element;
}> = [
  { key: "home", label: "오늘의 책상", mobileLabel: "책상", icon: HomeIcon },
  { key: "reading", label: "원문 읽기", mobileLabel: "읽기", icon: BookIcon },
  { key: "vocab", label: "내 단어장", mobileLabel: "단어", icon: CardFileIcon },
  { key: "study", label: "복습", icon: CardsIcon },
  { key: "shared", label: "덱 책장", mobileLabel: "덱", icon: BookshelfIcon },
  // No shorter form: the approved C pad shows "학습 계획" in the desktop
  // toolbar too, and the mobile drawer always uses the full label.
  { key: "plan", label: "학습 계획", icon: PencilIcon },
  { key: "info", label: "통계", icon: ClockIcon },
];

function createEmptySessionCounts(): SessionReviewCounts {
  return { again: 0, hard: 0, good: 0, easy: 0 };
}

// Shared by the single-word status click and the reading-tab bulk-save
// buttons: update the matching vocab item if the word is already saved in
// this deck, otherwise create it -- reusing the same base_form ->
// normalized_form -> surface matching policy as the coverage dashboard.
// example_sentence is only ever filled in when the existing item's is
// blank, never overwritten.
async function persistReadingToken(
  token: TokenWithStatus,
  deckIdNumber: number,
  status: TokenStatus,
  existingItems: VocabItem[],
): Promise<VocabItem> {
  const key = getTokenGroupKey(token);
  const existing = existingItems.find(
    (item) => item.deck_id === deckIdNumber && getTokenGroupKey(item) === key,
  );

  if (existing) {
    const patchBody: { status: TokenStatus; example_sentence?: string } = {
      status,
    };
    if (!existing.example_sentence && token.example_sentence) {
      patchBody.example_sentence = token.example_sentence;
    }
    return requestJson<VocabItem>(`/vocab-items/${existing.id}`, {
      method: "PATCH",
      body: JSON.stringify(patchBody),
    });
  }

  return requestJson<VocabItem>("/vocab-items", {
    method: "POST",
    body: JSON.stringify({ ...token, status, deck_id: deckIdNumber }),
  });
}

// A just-persisted vocab item's id/meaning/example didn't used to make it
// back onto the in-memory reading token that triggered the save -- only
// readingDeckVocabItems got updated, so TokenDetailSheet (which reads
// token.savedVocabItemId directly) kept treating a freshly auto-saved word
// as unsaved until the reading session was reloaded/re-analyzed (Phase 99).
function applySavedVocabItemToToken(
  token: TokenWithStatus,
  saved: VocabItem,
): TokenWithStatus {
  return {
    ...token,
    status: saved.status,
    isClassified: true,
    savedVocabItemId: saved.id,
    savedMeaningKo: saved.meaning_ko || null,
    savedExampleSentence: saved.example_sentence || null,
  };
}

function createBlankVocabForm(deckId = ""): VocabFormData {
  return {
    surface: "",
    base_form: "",
    reading: "",
    part_of_speech: "",
    meaning_ko: "",
    dictionary_gloss: "",
    quality_tag: "normal",
    example_sentence: "",
    context_explanation_ko: "",
    status: "unknown",
    deck_id: deckId,
  };
}

function createBlankCustomTermForm(deckId = ""): CustomTermFormData {
  return {
    term: "",
    reading: "",
    part_of_speech: "명사",
    meaning_ko: "",
    description: "",
    deck_id: deckId,
  };
}

function customTermToForm(term: CustomTerm): CustomTermFormData {
  return {
    term: term.term,
    reading: term.reading,
    part_of_speech: term.part_of_speech,
    meaning_ko: term.meaning_ko,
    description: term.description,
    deck_id: term.deck_id === null ? "" : String(term.deck_id),
  };
}

function vocabItemToForm(item: VocabItem): VocabFormData {
  return {
    surface: item.surface,
    base_form: item.base_form,
    reading: item.reading,
    part_of_speech: item.part_of_speech,
    meaning_ko: item.meaning_ko,
    dictionary_gloss: item.dictionary_gloss,
    quality_tag: item.quality_tag,
    example_sentence: item.example_sentence,
    context_explanation_ko: item.context_explanation_ko,
    status: item.status,
    deck_id: String(item.deck_id),
  };
}

// 읽기 원문·상태의 기기 저장은 readingSessionStorage.ts(v3, 백엔드 환경 +
// 계정/방문자별 키)가 맡는다. 옛 공통 키(reading-session-v1)는 여기서 자동
// 복원·쓰기·삭제하지 않고, 복구 안내에서 읽기·복사·다운로드만 한다.
const READING_STORAGE_SCOPE = learningPlanStorageScope(API_BASE_URL);
const MAX_MEANING_KO_LENGTH = 200;

function getReadingStorageEnv(): ReadingStorageEnv {
  let storage: Storage | null = null;
  try {
    storage = typeof window === "undefined" ? null : window.localStorage;
  } catch {
    storage = null;
  }
  const locks =
    typeof navigator !== "undefined" && navigator.locks && typeof navigator.locks.request === "function"
      ? (navigator.locks as unknown as ReadingStorageEnv["locks"])
      : null;
  return { storage, locks };
}

function emptyReadingData(): ReadingSessionData {
  return {
    originalText: "",
    analyzedText: "",
    deckId: "",
    tokens: [],
    selectedTokenKey: null,
    message: "",
    isTextCollapsed: true,
    recentlySavedVocabItemIds: [],
    scrollFraction: null,
    tabletDocumentScrollFraction: null,
  };
}

function isEmptyReadingData(data: ReadingSessionData): boolean {
  return !data.originalText.trim() && !data.analyzedText && data.tokens.length === 0;
}

function readingDataJson(data: ReadingSessionData): string {
  return JSON.stringify(data);
}

function triggerDownload(file: ReadingDownload) {
  const blob = new Blob([file.content], { type: file.mimeType });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = file.fileName;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 0);
}

function readingSaveFailureMessage(result: SaveResult): string {
  const previous =
    "previous" in result
      ? result.previous === "kept"
        ? "이전에 저장한 내용은 그대로 있어요."
        : result.previous === "none"
          ? "아직 이 기기에 저장된 내용이 없어서, 창을 닫으면 지금 글이 사라져요."
          : "이전 저장본이 남아 있는지는 확인하지 못했어요."
      : "";
  if (result.kind === "tooLarge") {
    return `글이 너무 길어(20만 자 초과) 이 기기에 저장하지 않았어요. ${previous}`;
  }
  if (result.kind === "error") {
    const cause =
      result.reason === "quota"
        ? "브라우저 저장 공간이 부족해"
        : result.reason === "denied"
          ? "브라우저가 저장을 막아"
          : result.reason === "lock_failed"
            ? "저장 잠금을 얻지 못해"
            : result.reason === "unavailable"
              ? "저장된 내용을 확인하지 못해"
              : result.reason === "not_persisted"
                ? "저장이 반영되지 않아"
                : "알 수 없는 문제로";
    return `${cause} 이 기기에 저장하지 못했어요. ${previous}`;
  }
  return "";
}

type ReadingAccount = { epoch: number; owner: ReadingOwner | null };

// Shared by a fresh /analyze response and by session restore (re-deriving
// from freshly-fetched deck items rather than trusting possibly-stale
// persisted status).
function deriveReadingTokens(
  baseTokens: Token[],
  deckItems: VocabItem[],
  deckId: string,
): TokenWithStatus[] {
  return baseTokens.map((token) => {
    const base: TokenWithStatus = {
      ...token,
      status: "unclassified",
      isClassified: false,
    };
    const status = getTokenStatus(base, deckItems, deckId);
    const key = getTokenGroupKey(base);
    const savedItem = deckItems.find((item) => getTokenGroupKey(item) === key);
    return {
      ...base,
      status,
      isClassified: status !== "unclassified",
      savedExampleSentence: savedItem?.example_sentence || null,
      savedMeaningKo: savedItem?.meaning_ko || null,
      savedVocabItemId: savedItem?.id ?? null,
    };
  });
}

export default function HomePage() {
  const [activeTab, setActiveTab] = useState<TabKey>("home");
  const [decks, setDecks] = useState<Deck[]>([]);
  const [isLoadingDecks, setIsLoadingDecks] = useState(false);
  // Separate from deckMessage, which doubles as 단어 탭 CRUD feedback and only
  // renders there -- the reading tab needs its own failure signal it can put a
  // retry button next to.
  const [deckLoadError, setDeckLoadError] = useState("");
  // "" = no deck chosen yet on the 단어 탭 (see the vocab-list effect below) --
  // distinct from "all", which is an explicit "전체 단어장" choice. Keeping
  // these separate is what lets the tab open without an eager full fetch:
  // nothing loads until the user picks something, "all" included.
  const [selectedVocabDeckId, setSelectedVocabDeckId] = useState("");
  const [selectedStudyDeckId, setSelectedStudyDeckId] = useState("all");
  const [studyMode, setStudyMode] = useState<StudyMode>("today");
  const [vocabSearch, setVocabSearch] = useState("");
  const [vocabStatusFilter, setVocabStatusFilter] =
    useState<VocabStatusFilter>("all");
  const [vocabDueOnly, setVocabDueOnly] = useState(false);
  const [vocabSort, setVocabSort] = useState<VocabSort>("created_desc");
  const [newDeckName, setNewDeckName] = useState("");
  const [newDeckDescription, setNewDeckDescription] = useState("");
  const [newVocabForm, setNewVocabForm] = useState<VocabFormData>(
    createBlankVocabForm(),
  );
  const [isNewVocabFormOpen, setIsNewVocabFormOpen] = useState(false);
  const [customTerms, setCustomTerms] = useState<CustomTerm[]>([]);
  const [newCustomTermForm, setNewCustomTermForm] =
    useState<CustomTermFormData>(createBlankCustomTermForm());
  const [editCustomTermForm, setEditCustomTermForm] =
    useState<CustomTermFormData>(createBlankCustomTermForm());
  const [isCustomTermFormOpen, setIsCustomTermFormOpen] = useState(false);
  const [editingCustomTermId, setEditingCustomTermId] = useState<number | null>(
    null,
  );
  const [isSavingCustomTerm, setIsSavingCustomTerm] = useState(false);
  const [editingItemId, setEditingItemId] = useState<number | null>(null);
  const [editVocabForm, setEditVocabForm] = useState<VocabFormData>(
    createBlankVocabForm(),
  );
  const [isCreatingDeck, setIsCreatingDeck] = useState(false);
  const [readingText, setReadingText] = useState("");
  // Snapshot of the exact text that produced readingTokens -- kept separate
  // from readingText (the live textarea value) so the original-layout
  // reconstruction stays stable even if the user edits the textarea again
  // after analyzing without re-analyzing. Lives only in this in-memory
  // component state; never sent anywhere beyond the one /analyze call.
  const [analyzedReadingText, setAnalyzedReadingText] = useState("");
  const [readingSelectedDeckId, setReadingSelectedDeckId] = useState("");
  const [readingTokens, setReadingTokens] = useState<TokenWithStatus[]>([]);
  const [readingDeckVocabItems, setReadingDeckVocabItems] = useState<VocabItem[]>(
    [],
  );
  const [isReadingAnalyzing, setIsReadingAnalyzing] = useState(false);
  // Non-null only while a multi-chunk analysis is in flight -- drives the
  // "N / total 조각 분석 중" progress UI. Left null for the common short-text
  // case (single chunk) so nothing changes there.
  const [readingAnalyzeProgress, setReadingAnalyzeProgress] =
    useState<ChunkAnalyzeProgress | null>(null);
  const readingAnalyzeAbortRef = useRef<AbortController | null>(null);
  const [readingMessage, setReadingMessage] = useState("");
  // Soft, separate notice for "couldn't persist to localStorage" -- kept out
  // of readingMessage so it never clobbers the analyze/save result message.
  const [readingStorageWarning, setReadingStorageWarning] = useState("");
  // V3 content-canvas pass: default true (was false) -- previously the
  // input textarea/deck-picker stayed expanded above the reader by default
  // even after a successful analyze, so the "입력창" outweighed the reader
  // paper on first read. showForm in ReadingTab is `!hasResult ||
  // !isTextCollapsed`, so this only affects the state *after* a result
  // exists -- the very first empty-state input (hasResult === false) still
  // always shows regardless of this value. A restored session's own saved
  // isTextCollapsed value still overrides this on load below.
  const [isReadingTextCollapsed, setIsReadingTextCollapsed] = useState(true);
  const [isSavingReadingBatch, setIsSavingReadingBatch] = useState(false);
  const [recentlySavedVocabItemIds, setRecentlySavedVocabItemIds] = useState<
    number[]
  >([]);
  const [currentSelectedTokenKey, setCurrentSelectedTokenKey] = useState<
    string | null
  >(null);
  // Doubles as both the restore bookmark (passed down as
  // ReaderMode's initialScrollFraction, applied once) and the live value
  // ReaderMode echoes back up as the user scrolls (for persistence) --
  // same pattern currentSelectedTokenKey already uses.
  const [readingScrollFraction, setReadingScrollFraction] = useState<
    number | null
  >(null);
  const [readingTabletDocumentScrollFraction, setReadingTabletDocumentScrollFraction] = useState<
    number | null
  >(null);
  const [isReadingSessionRestored, setIsReadingSessionRestored] =
    useState(false);
  // ---- 읽기 기기 저장 경계 (Gate C) ----
  // 어느 owner(계정/방문자)의 읽기 자료를 열지: /me 또는 로그인 응답으로
  // 확인한 계정과 그 account epoch. owner null = 확인 실패(복원·저장 금지).
  const [readingAccount, setReadingAccount] = useState<ReadingAccount | null>(null);
  // 지금 화면에 복원(hydrate)된 owner 키. 이 키와 확인한 owner가 같아야 읽기
  // 지면을 보여 주고 자동 저장한다.
  const [readingHydratedKey, setReadingHydratedKey] = useState<string | null>(null);
  const readingKeyRef = useRef<string | null>(null);
  const readingOwnerRef = useRef<ReadingOwner | null>(null);
  // 계정 경계·다른 창 자료 불러오기마다 바뀐다. ReadingTab key와 읽기 요청
  // 가드에 쓴다.
  const readingGenerationRef = useRef(0);
  const [readingGeneration, setReadingGeneration] = useState(0);
  // 이 창이 마지막으로 확인한 저장 버전(키 없음 = null)과 그때의 내용.
  const readingBaseRef = useRef<ReadingSessionVersion | null>(null);
  const readingPersistedJsonRef = useRef<string | null>(null);
  // 확인하지 못한 마지막 저장소 시도(저장 내용 또는 삭제). 재확인 판단에 쓴다.
  const readingLastAttemptRef = useRef<LastStorageAttempt>(null);
  const [readingLastAttemptKind, setReadingLastAttemptKind] = useState<"save" | "remove">("save");
  // 읽기 작업 ID: 계정 경계뿐 아니라 새 원문(초기화)·원문 교체·새 분석·복원마다
  // 바뀐다. 이전 작업의 늦은 응답·catch·finally가 새 작업을 바꾸지 않게 한다.
  const readingWorkIdRef = useRef(0);
  const readingSelectedDeckIdRef = useRef("");
  // 같은 종류 요청이 겹칠 때 마지막 요청만 결과·진행 표시를 바꾼다.
  const readingDeckRequestSeqRef = useRef(createRequestSequence());
  const readingBatchSeqRef = useRef(createRequestSequence());
  const meaningEditSeqRef = useRef(createRequestSequence());
  const feedbackSeqRef = useRef(createRequestSequence());
  const [readingStorageStatus, setReadingStorageStatus] =
    useState<ReadingStorageStatus>("ready");
  const readingStorageStatusRef = useRef<ReadingStorageStatus>("ready");
  const readingSaveChainRef = useRef<Promise<unknown>>(Promise.resolve());
  // 저장하지 못한 편집: 그 owner 키에만 묶어 이 창 메모리에만 둔다.
  const readingRecoveryRef = useRef(new Map<string, ReadingSessionData>());
  const [readingRecoveryAvailable, setReadingRecoveryAvailable] = useState(false);
  const [readingRecoveryOffer, setReadingRecoveryOffer] =
    useState<ReadingRecoveryOffer | null>(null);
  const [readingNoticeMessage, setReadingNoticeMessage] = useState("");
  const [isReadingNoticeBusy, setIsReadingNoticeBusy] = useState(false);
  // 덱 확인 요청 진행 표시(요청 순번별). 덱을 바꾸면 이전 덱 요청은 무효가 된다.
  const [isReadingDeckConfirmBusy, setIsReadingDeckConfirmBusy] = useState(false);
  // 전체 사본을 가져온 뒤, 이 계정의 덱을 다시 확인하기 전에는 서버 저장 금지.
  const [readingDeckConfirmRequired, setReadingDeckConfirmRequired] = useState(false);
  const [readingSwitchPrompt, setReadingSwitchPrompt] = useState<{
    reason: string;
    resolve: (proceed: boolean) => void;
  } | null>(null);
  const readingSwitchPromptRef = useRef<{ resolve: (proceed: boolean) => void } | null>(null);
  const [vocabItems, setVocabItems] = useState<VocabItem[]>([]);
  // 렌더마다 갱신되는 지금 읽기 상태의 저장용 스냅샷(비동기 저장·경계에서 읽음).
  const readingDataRef = useRef<ReadingSessionData>(emptyReadingData());
  readingSelectedDeckIdRef.current = readingSelectedDeckId;
  readingDataRef.current = {
    originalText: readingText,
    analyzedText: analyzedReadingText,
    // 가져온 분류의 덱을 확인하기 전에는 덱 연결을 저장하지 않는다(새로고침해도
    // 확인을 다시 요구하도록).
    deckId: readingDeckConfirmRequired ? "" : readingSelectedDeckId,
    tokens: readingTokens,
    selectedTokenKey: currentSelectedTokenKey,
    message: readingMessage,
    isTextCollapsed: isReadingTextCollapsed,
    recentlySavedVocabItemIds,
    scrollFraction: readingScrollFraction,
    tabletDocumentScrollFraction: readingTabletDocumentScrollFraction,
  };
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [isAddingVocab, setIsAddingVocab] = useState(false);
  const [isUpdatingVocab, setIsUpdatingVocab] = useState(false);
  // Lightweight "내 단어장 뜻 수정" -- separate from the full editingItemId/
  // editVocabForm flow above so a quick meaning-only fix (from the vocab
  // list, reading tab, or study card) never risks touching surface/
  // base_form/reading/status/example_sentence via a stale full-form payload.
  const [meaningEditItemId, setMeaningEditItemId] = useState<number | null>(
    null,
  );
  const [meaningEditDraft, setMeaningEditDraft] = useState("");
  const meaningEditItemIdRef = useRef<number | null>(null);
  meaningEditItemIdRef.current = meaningEditItemId;
  const [isSavingMeaningEdit, setIsSavingMeaningEdit] = useState(false);
  const [meaningEditMessage, setMeaningEditMessage] = useState("");
  // "뜻 오류 신고" -- one shared modal, openable from any of the same three
  // places, tracked centrally so only one report can be in progress at once.
  const [meaningFeedbackTarget, setMeaningFeedbackTarget] =
    useState<MeaningFeedbackTarget | null>(null);
  const meaningFeedbackTargetRef = useRef<MeaningFeedbackTarget | null>(null);
  meaningFeedbackTargetRef.current = meaningFeedbackTarget;
  const [feedbackSuggestedMeaning, setFeedbackSuggestedMeaning] =
    useState("");
  const [feedbackReason, setFeedbackReason] = useState("");
  const [isSubmittingFeedback, setIsSubmittingFeedback] = useState(false);
  const [feedbackMessage, setFeedbackMessage] = useState("");
  // App-wide "피드백" -- separate from the word-meaning report above; posts
  // to /feedback/app instead of /feedback/meaning.
  const [isAppFeedbackOpen, setIsAppFeedbackOpen] = useState(false);
  const [appFeedbackCategory, setAppFeedbackCategory] =
    useState<AppFeedbackCategory>("bug");
  const [appFeedbackDraft, setAppFeedbackDraft] = useState("");
  const [isSubmittingAppFeedback, setIsSubmittingAppFeedback] = useState(false);
  const [appFeedbackResultMessage, setAppFeedbackResultMessage] = useState("");
  const [isLoadingVocab, setIsLoadingVocab] = useState(false);
  const [isExportingCsv, setIsExportingCsv] = useState(false);
  const [isExportingDeckPackage, setIsExportingDeckPackage] = useState(false);
  const [isImportingDeckPackage, setIsImportingDeckPackage] = useState(false);
  const [deckPackageFile, setDeckPackageFile] = useState<File | null>(null);
  const [isLoadingStudy, setIsLoadingStudy] = useState(false);
  const [isReviewing, setIsReviewing] = useState(false);
  const [message, setMessage] = useState("");
  const [vocabMessage, setVocabMessage] = useState("");
  const [deckMessage, setDeckMessage] = useState("");
  const [studyMessage, setStudyMessage] = useState("");
  const [studyStatsMessage, setStudyStatsMessage] = useState("");
  const [infoStatsMessage, setInfoStatsMessage] = useState("");
  const [studyItems, setStudyItems] = useState<StudyCardItem[]>([]);
  const [studyStats, setStudyStats] = useState<StudyStats | null>(null);
  const [infoStats, setInfoStats] = useState<StudyStats | null>(null);
  // 기록 탭 전용 read-only word highlights ("최근 담은 단어" / "자주 틀린
  // 단어") -- deliberately separate state from the Vocab tab's own
  // `vocabItems` (and its search/status/dueOnly/sort filters) so visiting
  // 기록 never re-triggers or overwrites whatever the Vocab tab's list/
  // filters currently show. Same existing /vocab-items endpoint and sort
  // values the Vocab tab already uses (created_desc/wrong_desc), just a
  // second, independent read of it for this screen's log-style summary.
  const [infoRecentWords, setInfoRecentWords] = useState<VocabItem[]>([]);
  const [infoHardWords, setInfoHardWords] = useState<VocabItem[]>([]);
  const [isLoadingInfoWords, setIsLoadingInfoWords] = useState(false);
  const [currentStudyIndex, setCurrentStudyIndex] = useState(0);
  const [isAnswerVisible, setIsAnswerVisible] = useState(false);
  const [sessionCounts, setSessionCounts] = useState<SessionReviewCounts>(
    createEmptySessionCounts(),
  );
  const [nextUpcomingReviewAt, setNextUpcomingReviewAt] = useState<string | null>(
    null,
  );
  const [againNextReviewAt, setAgainNextReviewAt] = useState<string | null>(null);
  const answerShownAtRef = useRef<number | null>(null);
  // 학습 계획 실행(Gate C-1b)의 세션 보호용 식별자. 세션을 새로 시작·교체·
  // 초기화할 때마다 바뀐다. 카드 진행은 currentStudyIndex로 따로 본다.
  const studySessionIdRef = useRef(0);
  const [hasStartedStudy, setHasStartedStudy] = useState(false);
  const [isLoadingStudyStats, setIsLoadingStudyStats] = useState(false);
  const [isLoadingInfoStats, setIsLoadingInfoStats] = useState(false);
  // Stats tab account boundary: bumped whenever the signed-in account (or
  // its token) changes. StudyLogPage is keyed on it, and the stats loaders
  // drop responses that started under an older account.
  const [statsAccountEpoch, setStatsAccountEpoch] = useState(0);
  // 학습 계획 계정 경계: currentUser·덱 목록이 어느 account epoch에서 왔는지.
  // 지금 epoch과 다르면(로그인·로그아웃·만료 직후) 계획 화면에는 계정/덱이
  // 없는 것으로 넘겨 이전 계정의 계획·덱이 한 프레임도 쓰이지 않게 한다.
  const [currentUserEpoch, setCurrentUserEpoch] = useState<number | null>(null);
  const [decksEpoch, setDecksEpoch] = useState<number | null>(null);
  const [sharedDecksEpoch, setSharedDecksEpoch] = useState<number | null>(null);
  // 학습 계획의 미저장 편집(탭 왕복용). 메모리에만 있고 기기에 쓰지 않으며,
  // 계정 경계(resetStatsForAccountChange)에서 즉시 비운다.
  const planDraftMemoryRef = useRef(new Map<string, PlanDraftMemoryEntry>());
  const planDraftMemory = useRef<PlanDraftMemory>({
    read: (key) => planDraftMemoryRef.current.get(key) ?? null,
    write: (key, entry) => {
      if (entry) planDraftMemoryRef.current.set(key, entry);
      else planDraftMemoryRef.current.delete(key);
    },
  }).current;
  const statsAccountEpochRef = useRef(0);
  const [currentUser, setCurrentUser] = useState<CurrentUser | null>(null);
  const [isLoadingCurrentUser, setIsLoadingCurrentUser] = useState(false);
  const [isAccountMenuOpen, setIsAccountMenuOpen] = useState(false);
  const [authMode, setAuthMode] = useState<"login" | "register">("login");
  const [authEmail, setAuthEmail] = useState("");
  const [authPassword, setAuthPassword] = useState("");
  const [authDisplayName, setAuthDisplayName] = useState("");
  const [authMessage, setAuthMessage] = useState("");
  const [isSubmittingAuth, setIsSubmittingAuth] = useState(false);
  const [sharedDecks, setSharedDecks] = useState<SharedDeckSummary[]>([]);
  const [selectedSharedDeck, setSelectedSharedDeck] =
    useState<SharedDeckDetail | null>(null);
  const [selectedSharedDeckId, setSelectedSharedDeckId] = useState<number | null>(
    null,
  );
  const [isLoadingSharedDecks, setIsLoadingSharedDecks] = useState(false);
  const [isLoadingSharedDeckDetail, setIsLoadingSharedDeckDetail] =
    useState(false);
  const [sharedDeckMessage, setSharedDeckMessage] = useState("");
  const [importingSharedDeckId, setImportingSharedDeckId] = useState<number | null>(
    null,
  );
  const [importedSharedDeckId, setImportedSharedDeckId] = useState<number | null>(
    null,
  );
  const [unpublishingSharedDeckId, setUnpublishingSharedDeckId] = useState<
    number | null
  >(null);
  const [republishingSharedDeckId, setRepublishingSharedDeckId] = useState<
    number | null
  >(null);
  // Subscribed shared-deck word status (see
  // docs/architecture/shared-lexeme-progress-storage.md) -- tracks only
  // which single lexeme_id is currently being saved, never a personal
  // vocab_items id.
  const [updatingWordLexemeId, setUpdatingWordLexemeId] = useState<
    number | null
  >(null);
  const [publishTitle, setPublishTitle] = useState("");
  const [publishDescription, setPublishDescription] = useState("");
  const [isPublishingDeck, setIsPublishingDeck] = useState(false);

  function resetStudySession() {
    studySessionIdRef.current += 1;
    setIsLoadingStudy(false);
    setStudyItems([]);
    setCurrentStudyIndex(0);
    setHasStartedStudy(false);
    setIsAnswerVisible(false);
    setStudyMessage("");
    setSessionCounts(createEmptySessionCounts());
    setNextUpcomingReviewAt(null);
    setAgainNextReviewAt(null);
    answerShownAtRef.current = null;
  }

  useEffect(() => {
    void initializeUserSession();
    // 이전 분류 초안(classification-draft)은 여기서 읽거나 지우지 않는다.
    // 학습 계획 탭의 LegacyClassificationDraftNotice가 사용자가 고를 때만
    // 보관·읽기 열기·삭제를 한다(깨진 초안 자동 삭제 경로 제거, Gate D).

    // 읽기 자료는 여기서 복원하지 않는다. 계정(owner)을 확인한 뒤
    // hydrateReadingForOwner가 그 owner의 v3 키만 연다.
  }, []);

  // 계정 확인 → 해당 owner 자료 복원 → 자동 저장 활성화.
  const readingOwnerKey =
    readingAccount && readingAccount.epoch === statsAccountEpoch && readingAccount.owner
      ? readingSessionKey(READING_STORAGE_SCOPE, readingAccount.owner)
      : null;
  const readingGateState: "pending" | "failed" | "ready" =
    !readingAccount || readingAccount.epoch !== statsAccountEpoch
      ? "pending"
      : readingAccount.owner
        ? "ready"
        : "failed";

  useEffect(() => {
    if (!readingOwnerKey || !readingAccount?.owner) return;
    if (readingKeyRef.current === readingOwnerKey) return;
    const owner = readingAccount.owner;
    const key = readingOwnerKey;
    const epoch = statsAccountEpochRef.current;
    let cancelled = false;
    // 경계에서 시작한 이전 owner 저장(같은 계정이면 같은 키)이 끝난 뒤에 연다.
    void readingSaveChainRef.current.then(() => {
      if (cancelled || statsAccountEpochRef.current !== epoch || readingKeyRef.current !== null) return;
      hydrateReadingForOwner(owner, key);
    });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [readingOwnerKey, statsAccountEpoch]);

  // Debounced auto-save (600ms), 복원이 끝난 현재 owner 키에만. 바뀐 내용이
  // 없거나, 빈 영역을 처음 연 상태(빈 세션)면 저장하지 않는다.
  useEffect(() => {
    const key = readingKeyRef.current;
    if (!key || readingHydratedKey !== key) return;
    if (readingStorageStatusRef.current !== "ready") return;
    const generation = readingGenerationRef.current;
    const timeoutId = window.setTimeout(() => {
      void queueReadingSave(key, generation);
    }, 600);
    return () => window.clearTimeout(timeoutId);
  }, [
    readingHydratedKey,
    readingText,
    analyzedReadingText,
    readingSelectedDeckId,
    readingTokens,
    currentSelectedTokenKey,
    readingMessage,
    isReadingTextCollapsed,
    recentlySavedVocabItemIds,
    readingScrollFraction,
    readingTabletDocumentScrollFraction,
  ]);

  // 안내 카드의 결과 문구는 잠시 보여 주고 지운다(상태 안내는 따로 남는다).
  useEffect(() => {
    if (!readingNoticeMessage) return;
    const timeoutId = window.setTimeout(() => setReadingNoticeMessage(""), 6000);
    return () => window.clearTimeout(timeoutId);
  }, [readingNoticeMessage]);

  // 복원 뒤 읽기 덱이 비어 있으면(빈 영역·원문만 복사·경계 직후) 지금 계정의
  // 덱 목록에서 기본 덱을 고른다. 덱 목록은 같은 account epoch에서 받은 것만 쓴다.
  useEffect(() => {
    if (!readingHydratedKey || readingSelectedDeckId) return;
    if (decksEpoch !== statsAccountEpoch || decks.length === 0) return;
    const fallback = decks.find((deck) => deck.name === "기본 단어장") ?? decks[0];
    setReadingSelectedDeckId(String(fallback.id));
  }, [readingHydratedKey, readingSelectedDeckId, decks, decksEpoch, statsAccountEpoch]);

  // 다른 창의 저장소 변경: 인증 키가 바뀌면 이 창도 계정 경계를 지난다.
  // 지금 owner의 읽기 키가 바뀌면 덮어쓰지 않도록 자동 저장을 멈추고 알린다.
  useEffect(() => {
    const onStorage = (event: StorageEvent) => {
      if (event.storageArea && event.storageArea !== window.localStorage) return;
      if (event.key === null || event.key === ACCESS_TOKEN_KEY) {
        handleExternalAuthChangeRef.current();
        return;
      }
      if (event.key === readingKeyRef.current && readingStorageStatusRef.current === "ready") {
        setReadingStorage("conflict");
        setReadingNoticeMessage("");
        // 목적지가 더는 비어 있지 않으므로 복사 제안도 거둔다.
        setReadingRecoveryOffer(null);
      }
    };
    window.addEventListener("storage", onStorage);
    return () => window.removeEventListener("storage", onStorage);
  }, []);

  function setReadingStorage(status: ReadingStorageStatus) {
    readingStorageStatusRef.current = status;
    setReadingStorageStatus(status);
  }

  function applyReadingData(data: ReadingSessionData, restored: boolean) {
    setReadingText(data.originalText);
    setAnalyzedReadingText(data.analyzedText);
    setReadingSelectedDeckId(data.deckId);
    setReadingTokens(data.tokens);
    setReadingMessage(data.message);
    setIsReadingTextCollapsed(data.isTextCollapsed);
    setRecentlySavedVocabItemIds(data.recentlySavedVocabItemIds);
    setCurrentSelectedTokenKey(data.selectedTokenKey);
    setReadingScrollFraction(data.scrollFraction);
    setReadingTabletDocumentScrollFraction(data.tabletDocumentScrollFraction);
    setIsReadingSessionRestored(restored);
    readingDataRef.current = data;
  }

  function clearReadingScreen() {
    setReadingText("");
    setAnalyzedReadingText("");
    setReadingSelectedDeckId("");
    setReadingTokens([]);
    setReadingDeckVocabItems([]);
    setReadingMessage("");
    setReadingStorageWarning("");
    setIsReadingTextCollapsed(true);
    setRecentlySavedVocabItemIds([]);
    setCurrentSelectedTokenKey(null);
    setReadingScrollFraction(null);
    setReadingTabletDocumentScrollFraction(null);
    setIsReadingSessionRestored(false);
    setIsReadingAnalyzing(false);
    setReadingAnalyzeProgress(null);
    setIsSavingReadingBatch(false);
    readingDataRef.current = emptyReadingData();
  }

  // 읽기 작업 교체: 이전 작업의 요청 결과를 무효화한다. 일괄 저장 진행 표시도
  // 이전 작업 것이므로 끈다(새 작업의 요청은 새 순번으로 다시 켠다).
  function bumpReadingWork() {
    readingWorkIdRef.current += 1;
    readingBatchSeqRef.current.invalidate();
    readingDeckRequestSeqRef.current.invalidate();
    setIsSavingReadingBatch(false);
    setIsReadingDeckConfirmBusy(false);
  }

  // 세대 교체: 작업 교체 + ReadingTab 자식 상태(바구니·검색·옵션)도 새로 만든다.
  function bumpReadingGeneration() {
    readingGenerationRef.current += 1;
    setReadingGeneration(readingGenerationRef.current);
    bumpReadingWork();
  }

  function abortReadingAnalysis() {
    readingAnalyzeAbortRef.current?.abort();
    readingAnalyzeAbortRef.current = null;
    setIsReadingAnalyzing(false);
    setReadingAnalyzeProgress(null);
  }

  // 읽기 요청 가드: 시작할 때의 owner 키·account epoch·읽기 작업 ID(와 덱)가
  // 그대로일 때만 응답·catch·finally를 적용한다.
  function captureReadingContext() {
    return captureReadingContextFrom({
      ownerKey: () => readingKeyRef.current,
      accountEpoch: () => statsAccountEpochRef.current,
      workId: () => readingWorkIdRef.current,
      deckId: () => readingSelectedDeckIdRef.current,
    });
  }

  // 저장소에서 읽은 세션을 화면에 적용하는 모든 경로(최초 복원·다른 창 내용
  // 불러오기·복사)가 같은 규칙을 쓴다. 덱 연결 없이 토큰만 있으면 덱 확인 요구.
  function applyStoredReadingSession(
    session: ReadingSessionData,
    version: ReadingSessionVersion,
    restored: boolean,
  ) {
    applyReadingData(session, restored);
    readingBaseRef.current = version;
    readingPersistedJsonRef.current = readingDataJson(session);
    const needsDeck = requiresDeckConfirmation(session);
    setReadingDeckConfirmRequired(needsDeck);
    if (!needsDeck && session.deckId && session.tokens.length > 0) {
      void refreshReadingDeckVocabItems(session.deckId, session.tokens);
    }
  }

  function hydrateReadingForOwner(owner: ReadingOwner, key: string) {
    const env = getReadingStorageEnv();
    readingKeyRef.current = key;
    readingOwnerRef.current = owner;
    readingBaseRef.current = null;
    readingPersistedJsonRef.current = null;
    readingLastAttemptRef.current = null;
    setReadingRecoveryOffer(null);
    setReadingNoticeMessage("");
    setReadingDeckConfirmRequired(false);
    abortReadingAnalysis();
    clearReadingScreen();
    bumpReadingGeneration();

    const capability = readingStorageCapability(env);
    let status: ReadingStorageStatus = capability === "full" ? "ready" : "readOnly";
    if (capability === "unavailable") {
      status = "unavailable";
    } else {
      const stored = readReadingSession(env, READING_STORAGE_SCOPE, owner);
      if (stored.kind === "ok") {
        applyStoredReadingSession(
          stored.value.session,
          { instanceId: stored.value.instanceId, revision: stored.value.revision },
          true,
        );
      } else if (stored.kind === "corrupt") {
        status = "corrupt";
      } else if (stored.kind === "unavailable") {
        status = "unavailable";
      } else {
        // 빈 영역: 이전 공통 자료나 방문자 자료가 있으면 복사를 제안만 한다.
        const legacy = readLegacyReadingSession(env);
        const guest =
          owner.kind === "user"
            ? readReadingSession(env, READING_STORAGE_SCOPE, { kind: "guest" })
            : null;
        const offer: ReadingRecoveryOffer = {
          legacy: legacy.kind === "ok" ? "ok" : legacy.kind === "corrupt" ? "corrupt" : null,
          legacyUpdatedAt: legacy.kind === "ok" ? legacy.value.updatedAt : null,
          guest:
            guest?.kind === "ok" && !isEmptyReadingData(guest.value.session),
          guestUpdatedAt: guest?.kind === "ok" ? guest.value.updatedAt : null,
        };
        if (offer.legacy || offer.guest) setReadingRecoveryOffer(offer);
      }
    }
    setReadingStorage(status);
    setReadingRecoveryAvailable(readingRecoveryRef.current.has(key));
    setReadingHydratedKey(key);
  }

  // 저장은 창 안에서 한 줄로 세운다(같은 base로 겹쳐 쓰지 않게).
  function queueReadingSave(key: string, generation: number): Promise<SaveResult | null> {
    const run = readingSaveChainRef.current.then(() => saveReadingNow(key, generation));
    readingSaveChainRef.current = run.catch(() => undefined);
    return run;
  }

  async function saveReadingNow(key: string, generation: number): Promise<SaveResult | null> {
    const owner = readingOwnerRef.current;
    if (!owner || readingKeyRef.current !== key || readingGenerationRef.current !== generation) {
      return null;
    }
    if (readingStorageStatusRef.current !== "ready") return null;
    const data = readingDataRef.current;
    const json = readingDataJson(data);
    if (json === readingPersistedJsonRef.current) {
      // 저장소가 이미 지금 내용과 같다: 남은 실패 안내는 더는 맞지 않는다.
      setReadingStorageWarning("");
      return { kind: "ok", version: readingBaseRef.current! };
    }
    // 빈 영역을 처음 연 상태 그대로면 빈 세션을 만들지 않는다(복구 목적지 보존).
    if (readingPersistedJsonRef.current === null && isEmptyReadingData(data)) return null;
    readingLastAttemptRef.current = { kind: "save", json };
    setReadingLastAttemptKind("save");
    const result = await saveReadingSession(getReadingStorageEnv(), {
      scope: READING_STORAGE_SCOPE,
      owner,
      base: readingBaseRef.current,
      session: data,
      isCurrent: () => readingKeyRef.current === key && readingGenerationRef.current === generation,
    });
    if (readingKeyRef.current !== key || readingGenerationRef.current !== generation) {
      return result;
    }
    handleReadingSaveResult(key, result, data, json);
    return result;
  }

  function handleReadingSaveResult(
    key: string,
    result: SaveResult,
    data: ReadingSessionData,
    json: string,
  ) {
    if (result.kind === "ok") {
      readingBaseRef.current = result.version;
      readingPersistedJsonRef.current = json;
      readingRecoveryRef.current.delete(key);
      setReadingStorageWarning("");
      // 이 영역에 처음 저장했으면 더는 빈 목적지가 아니므로 복사 제안을 거둔다.
      setReadingRecoveryOffer(null);
      return;
    }
    if (result.kind === "cancelled") return;
    readingRecoveryRef.current.set(key, data);
    if (result.kind === "conflict") {
      setReadingStorage("conflict");
    } else if (result.kind === "unverified") {
      // 확인 실패가 이전 쓰기 실패 안내를 대신한다(두 안내가 엇갈리지 않게).
      setReadingStorageWarning("");
      setReadingStorage("unverified");
    } else if (result.kind === "corrupt") {
      setReadingStorage("corrupt");
    } else if (result.kind === "unsupported") {
      setReadingStorage("readOnly");
    } else {
      setReadingStorageWarning(readingSaveFailureMessage(result));
    }
  }

  // 계정 경계: 이전 owner의 내용을 화면에서 즉시 지우고, 저장하지 못한 최신
  // 편집은 그 owner 키에만 묶어 둔다(가능하면 그 키에 바로 저장도 시도).
  function resetReadingForBoundary() {
    const key = readingKeyRef.current;
    const owner = readingOwnerRef.current;
    const data = readingDataRef.current;
    const json = readingDataJson(data);
    const dirty =
      key !== null &&
      json !== readingPersistedJsonRef.current &&
      !(readingPersistedJsonRef.current === null && isEmptyReadingData(data));
    if (key && owner && dirty) {
      readingRecoveryRef.current.set(key, data);
      if (readingStorageStatusRef.current === "ready") {
        const base = readingBaseRef.current;
        readingSaveChainRef.current = readingSaveChainRef.current
          .then(() =>
            saveReadingSession(getReadingStorageEnv(), {
              scope: READING_STORAGE_SCOPE,
              owner,
              base,
              session: data,
              isCurrent: () => true,
            }),
          )
          .then((result) => {
            if (result.kind === "ok") readingRecoveryRef.current.delete(key);
          })
          .catch(() => undefined);
      }
    }
    // 열려 있던 수동 전환 확인창과 그 대기 중 전환은 취소한다. 이전 확인으로
    // 새 계정을 로그아웃하거나 로그인하지 않는다.
    const pendingPrompt = readingSwitchPromptRef.current;
    readingSwitchPromptRef.current = null;
    setReadingSwitchPrompt(null);
    pendingPrompt?.resolve(false);
    abortReadingAnalysis();
    readingKeyRef.current = null;
    readingOwnerRef.current = null;
    readingBaseRef.current = null;
    readingPersistedJsonRef.current = null;
    readingLastAttemptRef.current = null;
    bumpReadingGeneration();
    clearReadingScreen();
    setReadingHydratedKey(null);
    setReadingStorage("ready");
    setReadingRecoveryOffer(null);
    setReadingRecoveryAvailable(false);
    setReadingNoticeMessage("");
    setIsReadingNoticeBusy(false);
    setReadingDeckConfirmRequired(false);
    // 읽기에서 열 수 있는 뜻 수정·신고 창도 이전 계정 것이므로 닫는다.
    setMeaningEditItemId(null);
    setMeaningEditDraft("");
    setMeaningEditMessage("");
    setMeaningFeedbackTarget(null);
    setIsSavingMeaningEdit(false);
    setIsSubmittingFeedback(false);
  }

  function hasUnsavedReadingEdits(): boolean {
    const key = readingKeyRef.current;
    if (!key) return false;
    const data = readingDataRef.current;
    const json = readingDataJson(data);
    if (json === readingPersistedJsonRef.current) return false;
    return !(readingPersistedJsonRef.current === null && isEmptyReadingData(data));
  }

  // 수동 계정 전환(로그인·로그아웃) 전: 최신 편집을 지금 owner에 저장하고,
  // 저장하지 못하면 머무르기 / 내려받기 / 계속을 묻는다. 내려받기는 전환
  // 승인이 아니다.
  async function prepareReadingForManualSwitch(): Promise<boolean> {
    const key = readingKeyRef.current;
    const epoch = statsAccountEpochRef.current;
    if (!key || !hasUnsavedReadingEdits()) return true;
    let reason = "";
    if (readingStorageStatusRef.current === "ready") {
      const result = await queueReadingSave(key, readingGenerationRef.current);
      // 저장을 기다리는 사이 만료·다른 창 변경으로 계정이 바뀌었으면 이 전환은 취소.
      if (statsAccountEpochRef.current !== epoch) return false;
      if (!hasUnsavedReadingEdits()) return true;
      reason =
        result && result.kind !== "ok"
          ? result.kind === "conflict"
            ? "다른 창에서 이 읽기 자료가 바뀌어 저장하지 않았어요."
            : result.kind === "unverified"
              ? "저장했는지 확인하지 못했어요."
              : readingSaveFailureMessage(result) || "이 기기에 저장하지 못했어요."
          : "이 기기에 저장하지 못했어요.";
    } else {
      reason =
        readingStorageStatusRef.current === "readOnly"
          ? "이 브라우저에서는 읽기 자료를 자동 저장할 수 없어요."
          : "지금 읽기 자료의 저장이 멈춰 있어요.";
    }
    const proceed = await new Promise<boolean>((resolve) => {
      readingSwitchPromptRef.current = { resolve };
      setReadingSwitchPrompt({ reason, resolve });
    });
    return proceed && statsAccountEpochRef.current === epoch;
  }

  function resolveReadingSwitch(proceed: boolean) {
    const prompt = readingSwitchPromptRef.current;
    readingSwitchPromptRef.current = null;
    setReadingSwitchPrompt(null);
    prompt?.resolve(proceed);
  }

  function readingOwnerLabel(): string {
    const owner = readingOwnerRef.current;
    if (!owner) return "";
    if (owner.kind === "guest") return "방문자";
    return currentUser?.display_name ? `${currentUser.display_name} 계정` : "이 계정";
  }

  async function copyIntoCurrentReading(source: "legacy" | "guest", mode: "textOnly" | "full") {
    const key = readingKeyRef.current;
    const owner = readingOwnerRef.current;
    if (!key || !owner || isReadingNoticeBusy) return;
    const env = getReadingStorageEnv();
    const read =
      source === "legacy"
        ? readLegacyReadingSession(env)
        : readReadingSession(env, READING_STORAGE_SCOPE, { kind: "guest" });
    if (read.kind !== "ok") {
      setReadingNoticeMessage("가져올 자료를 읽지 못했어요. 원래 자료는 그대로 있어요.");
      return;
    }
    const label = readingOwnerLabel();
    if (
      !window.confirm(
        `이 자료가 본인 것이 맞나요?\n${label}의 빈 읽기 영역으로 ${
          mode === "textOnly" ? "원문만" : "분류·위치까지"
        } 복사해요. 원래 자료는 지우지 않아요.`,
      )
    ) {
      return;
    }
    const ctx = captureReadingContext();
    setIsReadingNoticeBusy(true);
    try {
      const result = await copyToEmptyReadingSession(env, {
        scope: READING_STORAGE_SCOPE,
        owner,
        source: read.value.session,
        mode,
        isCurrent: ctx.isCurrent,
      });
      if (!ctx.isCurrent()) return;
      if (result.kind === "ok") {
        const stored = readReadingSession(env, READING_STORAGE_SCOPE, owner);
        if (stored.kind === "ok") {
          abortReadingAnalysis();
          bumpReadingGeneration();
          applyStoredReadingSession(stored.value.session, result.version, false);
        }
        setReadingRecoveryOffer(null);
        setReadingNoticeMessage(
          mode === "textOnly"
            ? "원문을 가져왔어요. 덱을 고르고 분석하기를 눌러 주세요."
            : "분류까지 가져왔어요. 이 계정의 덱을 확인하면 단어를 저장할 수 있어요.",
        );
      } else if (result.kind === "destinationExists") {
        setReadingRecoveryOffer(null);
        setReadingNoticeMessage("이 영역에 이미 읽기 자료가 있어 복사하지 않았어요.");
      } else if (result.kind === "unsupported") {
        setReadingNoticeMessage("이 브라우저에서는 복사할 수 없어요. 원자료를 내려받아 두세요.");
      } else if (result.kind === "unverified") {
        setReadingNoticeMessage("복사했는지 확인하지 못했어요. 새로고침해서 확인해 주세요.");
        setReadingStorage("unverified");
      } else if (result.kind !== "cancelled") {
        setReadingNoticeMessage("복사하지 못했어요. 원래 자료는 그대로 있어요.");
      }
    } finally {
      // 안내 버튼의 진행 표시는 결과 적용 여부와 무관하게 끝낸다.
      setIsReadingNoticeBusy(false);
    }
  }

  function downloadLegacyReadingRaw() {
    const raw = readLegacyReadingSessionRaw(getReadingStorageEnv());
    if (raw === null) {
      setReadingNoticeMessage("내려받을 이전 자료가 없어요.");
      return;
    }
    triggerDownload(rawBackupDownload(raw));
  }

  function downloadCurrentReadingText() {
    triggerDownload(originalTextDownload(readingDataRef.current));
  }

  function downloadStoredReadingRaw() {
    const key = readingKeyRef.current;
    if (!key) return;
    try {
      const raw = window.localStorage.getItem(key);
      if (raw !== null) triggerDownload(rawBackupDownload(raw));
    } catch {
      setReadingNoticeMessage("저장소를 읽지 못했어요.");
    }
  }

  // 충돌: 사용자가 고를 때만 저장된 내용을 이 창으로 불러온다(내 편집은 덮어쓰기
  // 전에 내려받을 수 있게 안내에 남는다).
  function loadStoredReadingIntoWindow() {
    const owner = readingOwnerRef.current;
    const key = readingKeyRef.current;
    if (!owner || !key) return;
    if (
      hasUnsavedReadingEdits() &&
      !window.confirm("이 창의 편집 대신 저장된 내용을 불러올까요? 이 창의 편집은 사라져요.")
    ) {
      return;
    }
    const stored = readReadingSession(getReadingStorageEnv(), READING_STORAGE_SCOPE, owner);
    abortReadingAnalysis();
    bumpReadingGeneration();
    if (stored.kind === "ok") {
      applyStoredReadingSession(
        stored.value.session,
        { instanceId: stored.value.instanceId, revision: stored.value.revision },
        true,
      );
      setReadingRecoveryOffer(null);
      setReadingStorage("ready");
    } else if (stored.kind === "empty") {
      clearReadingScreen();
      setReadingDeckConfirmRequired(false);
      readingBaseRef.current = null;
      readingPersistedJsonRef.current = null;
      setReadingStorage("ready");
    } else {
      setReadingStorage(stored.kind === "corrupt" ? "corrupt" : "unavailable");
    }
    readingRecoveryRef.current.delete(key);
    setReadingRecoveryAvailable(false);
    setReadingNoticeMessage("");
  }

  // 확인 실패: 저장된 값이 이 창이 마지막으로 쓰려던 내용과 같을 때만 그 버전을
  // 채택하고 자동 저장을 재개한다. 다르면 다른 창 자료일 수 있으므로 충돌로 둔다.
  function recheckReadingStorage() {
    const owner = readingOwnerRef.current;
    if (!owner) return;
    const stored = readReadingSession(getReadingStorageEnv(), READING_STORAGE_SCOPE, owner);
    const outcome = recheckAfterUnverified(stored, readingLastAttemptRef.current, readingDataJson);
    if (outcome.kind === "unavailable") {
      setReadingNoticeMessage("아직 저장소를 읽을 수 없어요.");
      return;
    }
    if (outcome.kind === "conflict") {
      setReadingStorage("conflict");
      setReadingNoticeMessage("");
      return;
    }
    if (outcome.kind === "adopt") {
      readingBaseRef.current = { instanceId: outcome.instanceId, revision: outcome.revision };
      readingPersistedJsonRef.current = outcome.json;
      setReadingNoticeMessage("저장된 것을 확인했어요. 자동 저장을 다시 시작해요.");
    } else {
      readingBaseRef.current = null;
      readingPersistedJsonRef.current = null;
      setReadingNoticeMessage("지워진 것을 확인했어요. 자동 저장을 다시 시작해요.");
    }
    readingLastAttemptRef.current = null;
    setReadingStorageWarning("");
    setReadingStorage("ready");
    // 확인을 기다리는 동안의 편집도 이어서 저장한다.
    if (readingKeyRef.current) void queueReadingSave(readingKeyRef.current, readingGenerationRef.current);
  }

  async function resetCorruptReadingStorage() {
    const owner = readingOwnerRef.current;
    if (!owner) return;
    if (!window.confirm("읽을 수 없는 이 영역의 읽기 자료를 지울까요? 먼저 원자료를 내려받아 둘 수 있어요.")) {
      return;
    }
    const ctx = captureReadingContext();
    readingLastAttemptRef.current = { kind: "remove" };
    setReadingLastAttemptKind("remove");
    const result = await removeReadingSession(getReadingStorageEnv(), {
      scope: READING_STORAGE_SCOPE,
      owner,
      expected: "corrupt",
      isCurrent: ctx.isCurrent,
    });
    if (!ctx.isCurrent()) return;
    if (result.kind === "ok") {
      readingBaseRef.current = null;
      readingPersistedJsonRef.current = null;
      readingLastAttemptRef.current = null;
      setReadingStorage("ready");
      setReadingNoticeMessage("지웠어요. 새로 읽을 수 있어요.");
    } else if (result.kind === "unverified") {
      // 지워졌을 수도 있다. 성공·보존 어느 쪽으로도 말하지 않고 재확인을 기다린다.
      setReadingStorage("unverified");
      setReadingNoticeMessage("");
    } else if (result.kind === "conflict") {
      setReadingStorage("conflict");
    } else if (result.kind !== "cancelled") {
      setReadingNoticeMessage("지우지 못했어요. 자료는 그대로 있어요.");
    }
  }

  function restoreReadingRecovery() {
    const key = readingKeyRef.current;
    if (!key) return;
    const snapshot = readingRecoveryRef.current.get(key);
    if (!snapshot) return;
    abortReadingAnalysis();
    bumpReadingGeneration();
    // 내용만 되살린다. 저장 버전(base)은 그대로라, 그사이 다른 창이 바꿨으면 충돌로 멈춘다.
    applyReadingData(snapshot, false);
    // 덱 확인 전이던 사본은 되살려도 덱 확인을 다시 요구한다(스냅샷의 덱은 비어 있다).
    setReadingDeckConfirmRequired(requiresDeckConfirmation(snapshot));
    readingRecoveryRef.current.delete(key);
    setReadingRecoveryAvailable(false);
  }

  function downloadReadingRecovery() {
    const key = readingKeyRef.current;
    const snapshot = key ? readingRecoveryRef.current.get(key) : null;
    if (snapshot) triggerDownload(originalTextDownload(snapshot));
  }

  function discardReadingRecovery() {
    const key = readingKeyRef.current;
    if (key) readingRecoveryRef.current.delete(key);
    setReadingRecoveryAvailable(false);
  }

  // 전체 사본: 사용자가 이 계정의 덱을 확인하면, 그 덱의 서버 항목과 일치하는
  // 단어만 서버 사실로 바꾸고 나머지는 가져온 로컬 분류로 둔다.
  async function confirmImportedReadingDeck() {
    const deckId = readingSelectedDeckIdRef.current;
    if (!deckId) return;
    const ctx = captureReadingContext();
    const seq = readingDeckRequestSeqRef.current.start();
    setIsReadingDeckConfirmBusy(true);
    try {
      const response = await requestJson<VocabItemsResponse>(`/vocab-items?deck_id=${deckId}`);
      // 요청 당시 덱이 지금도 선택돼 있고, 이 요청이 마지막일 때만 적용한다.
      if (!ctx.isCurrentForDeck() || !readingDeckRequestSeqRef.current.isLatest(seq)) return;
      const deckItems = response.items;
      setReadingDeckVocabItems(deckItems);
      setReadingTokens((current) => {
        const derived = deriveReadingTokens(current, deckItems, deckId);
        return current.map((token, index) =>
          derived[index].savedVocabItemId ? derived[index] : token,
        );
      });
      setReadingDeckConfirmRequired(false);
      setReadingNoticeMessage("이 계정의 덱과 연결했어요.");
    } catch (error) {
      if (!ctx.isCurrentForDeck() || !readingDeckRequestSeqRef.current.isLatest(seq)) return;
      setReadingNoticeMessage(getAuthAwareErrorMessage(error, "덱을 확인하지 못했어요."));
    } finally {
      // 마지막 요청만 진행 표시를 끈다(오래된 finally가 새 요청 표시를 끄지 않게).
      if (readingDeckRequestSeqRef.current.isLatest(seq)) setIsReadingDeckConfirmBusy(false);
    }
  }

  async function initializeUserSession() {
    await loadCurrentUser();
    await refreshUserScopedData();
  }

  const defaultDeck =
    decks.find((deck) => deck.name === "기본 단어장") ?? decks[0];
  const defaultVocabFormDeckId =
    selectedVocabDeckId !== "all" && selectedVocabDeckId !== ""
      ? selectedVocabDeckId
      : defaultDeck
        ? String(defaultDeck.id)
        : "";

  useEffect(() => {
    setNewVocabForm((currentForm) => ({
      ...currentForm,
      deck_id: defaultVocabFormDeckId,
    }));
    setNewCustomTermForm((currentForm) => ({
      ...currentForm,
      deck_id: selectedVocabDeckId !== "all" ? selectedVocabDeckId : "",
    }));
  }, [defaultVocabFormDeckId]);

  // Deck must be explicitly chosen ("all" counts, "" does not) before the
  // 단어 탭 fetches anything -- see selectedVocabDeckId's declaration above.
  useEffect(() => {
    if (activeTab === "vocab" && selectedVocabDeckId !== "") {
      void loadVocabItems();
      void loadCustomTerms();
    }
  }, [
    activeTab,
    selectedVocabDeckId,
    vocabSearch,
    vocabStatusFilter,
    vocabDueOnly,
    vocabSort,
  ]);

  // Home starts as the default tab and shows the same "오늘 학습" numbers
  // the study tab does, so it needs stats fetched up front rather than only
  // on a study-tab visit. Reuses the existing /stats fetch + state --
  // failures already surface as studyStatsMessage without throwing, so a
  // failed request here can't break the home screen. Also reuses
  // loadInfoWordHighlights (already built for the 기록 tab's "최근 담은
  // 단어" list) so Home's own index-card teaser has real words instead of
  // just a count -- same /vocab-items?sort=created_desc read, no new call.
  useEffect(() => {
    if (activeTab === "home") {
      void loadStudyStats(selectedStudyDeckId);
      void loadInfoWordHighlights();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeTab]);

  // The reading tab is reachable through several paths (nav/handleTabChange,
  // the 학습 계획 tab's old-draft "읽기에서 열기", home's 샘플 CTA, and a localStorage-restored
  // session), and decks are otherwise fetched only once on mount -- so a
  // failed first /decks call used to leave the deck select permanently empty
  // with no way back short of a page reload. Watching activeTab instead of
  // patching each entry point covers all of them, including future ones.
  // The ref bounds this to one automatic attempt per reading-tab visit, so a
  // response with no decks at all can't spin into a fetch loop; an actual
  // failure surfaces deckLoadError and the user's retry button re-requests.
  const readingDeckAutoLoadTriedRef = useRef(false);
  useEffect(() => {
    if (activeTab !== "reading") {
      readingDeckAutoLoadTriedRef.current = false;
      return;
    }
    if (decks.length > 0 || isLoadingDecks || readingDeckAutoLoadTriedRef.current) {
      return;
    }
    readingDeckAutoLoadTriedRef.current = true;
    void loadDecks();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeTab, decks.length, isLoadingDecks]);

  async function handleTabChange(tab: TabKey) {
    setActiveTab(tab);
    if (tab === "study") {
      void loadStudyStats(selectedStudyDeckId);
    }
    if (tab === "shared") {
      void loadSharedDecks();
    }
    if (tab === "info") {
      void loadInfoStats();
      void loadInfoWordHighlights();
    }
  }

  // Reloads only. The deck selections and the study session are reset once,
  // synchronously, at the account boundary (resetStatsForAccountChange), so a
  // refresh that finishes late can't clear a session started in the meantime,
  // and a refresh whose account changed stops after its current request.
  async function refreshUserScopedData() {
    await runAccountScopedRefresh(() => statsAccountEpochRef.current, [
      () => loadDecks(),
      () => loadStudyStats("all"),
      () => loadInfoStats(),
      () => loadInfoWordHighlights(),
      () => loadSharedDecks(),
    ]);
  }

  async function loadCurrentUser() {
    // Any sign-in, sign-out or expiry while /me is in flight bumps the
    // account epoch; a result from an older epoch must not touch the user,
    // the token or the message.
    const epoch = statsAccountEpochRef.current;
    const sentToken = getAccessToken();
    setIsLoadingCurrentUser(true);
    try {
      const user = await requestJson<CurrentUser>("/me");
      if (epoch === statsAccountEpochRef.current) {
        setCurrentUser(user);
        setCurrentUserEpoch(epoch);
        // 토큰 없이 받은 dev 사용자는 등록 계정이 아니라 방문자다.
        setReadingAccount({
          epoch,
          owner: user.auth_provider === "dev" ? { kind: "guest" } : { kind: "user", userId: user.id },
        });
      }
    } catch (error) {
      if (isHttpError(error, 401)) {
        // 토큰 없이 보낸 /me의 401은 만료 처리가 이어지지 않으므로, 확인 실패로
        // 둔다(읽기 복원·저장 금지, "다시 확인" 가능).
        if (!sentToken && epoch === statsAccountEpochRef.current) {
          setReadingAccount({ epoch, owner: null });
        }
        // A stale/invalid/tampered token. apiFetch already cleared it (only
        // if it is still the stored token) and fired AUTH_EXPIRED_EVENT,
        // whose handler resets the stats, falls back to the dev user and
        // shows the expiry message. A 401 for a token that has since been
        // replaced is simply ignored here.
        return;
      }
      if (epoch === statsAccountEpochRef.current) {
        setCurrentUser(null);
        setCurrentUserEpoch(epoch);
        // 확인 실패: 방문자로 임의 전환하지 않고 읽기 복원·저장을 멈춘다.
        setReadingAccount({ epoch, owner: null });
        setAuthMessage(getErrorMessage(error, "현재 사용자 정보를 불러오지 못했습니다."));
      }
    } finally {
      setIsLoadingCurrentUser(false);
    }
  }

  async function handleAuthSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const email = authEmail.trim();
    const password = authPassword;
    if (!email) {
      setAuthMessage("이메일을 입력해주세요.");
      return;
    }
    if (!EMAIL_FORMAT_PATTERN.test(email)) {
      setAuthMessage("올바른 이메일 형식으로 입력해주세요.");
      return;
    }
    if (!password) {
      setAuthMessage("비밀번호를 입력해주세요.");
      return;
    }
    if (authMode === "register" && password.length < AUTH_MIN_PASSWORD_LENGTH) {
      setAuthMessage(
        `비밀번호는 최소 ${AUTH_MIN_PASSWORD_LENGTH}자 이상 입력해주세요.`,
      );
      return;
    }

    // 지금 owner의 저장하지 못한 읽기 편집을 먼저 처리한다(취소하면 머문다).
    if (!(await prepareReadingForManualSwitch())) {
      return;
    }

    setIsSubmittingAuth(true);
    setAuthMessage("");
    try {
      const response = await requestJson<AuthResponse>(
        authMode === "login" ? "/auth/login" : "/auth/register",
        {
          method: "POST",
          body: JSON.stringify(
            authMode === "login"
              ? { email, password }
              : {
                  email,
                  password,
                  display_name: authDisplayName.trim(),
                },
          ),
        },
        { includeAuth: false },
      );
      setAccessToken(response.access_token);
      resetStatsForAccountChange();
      setCurrentUser(response.user);
      setCurrentUserEpoch(statsAccountEpochRef.current);
      setReadingAccount({
        epoch: statsAccountEpochRef.current,
        owner: { kind: "user", userId: response.user.id },
      });
      setAuthPassword("");
      setAuthMessage(
        authMode === "login"
          ? "로그인했습니다."
          : "회원가입이 완료되었습니다.",
      );
      setIsAccountMenuOpen(false);
      await refreshUserScopedData();
    } catch (error) {
      if (isHttpError(error, 401)) {
        setAuthMessage("이메일 또는 비밀번호를 다시 확인해주세요.");
      } else if (
        authMode === "register" &&
        error instanceof ApiError &&
        error.status === 400 &&
        error.detail.includes("email already exists")
      ) {
        setAuthMessage("이미 가입된 이메일일 수 있습니다. 로그인해보세요.");
      } else {
        setAuthMessage(
          authMode === "login"
            ? "로그인에 실패했습니다. 잠시 후 다시 시도해주세요."
            : "회원가입에 실패했습니다. 잠시 후 다시 시도해주세요.",
        );
      }
    } finally {
      setIsSubmittingAuth(false);
    }
  }

  async function handleLogout() {
    if (!(await prepareReadingForManualSwitch())) {
      return;
    }
    clearAccessToken();
    resetStatsForAccountChange();
    setAuthPassword("");
    setAuthMessage("로그아웃했습니다. 개발 모드 데이터로 전환합니다.");
    await loadCurrentUser();
    await refreshUserScopedData();
  }

  async function loadDecks() {
    const epoch = statsAccountEpochRef.current;
    setIsLoadingDecks(true);
    try {
      const data = await requestJson<DecksResponse>("/decks");
      if (epoch !== statsAccountEpochRef.current) return;
      setDeckLoadError("");
      setDecks(data.items);
      setDecksEpoch(epoch);
      const defaultDeck =
        data.items.find((deck) => deck.name === "기본 단어장") ?? data.items[0];
      setReadingSelectedDeckId((currentDeckId) =>
        data.items.some((deck) => String(deck.id) === currentDeckId)
          ? currentDeckId
          : defaultDeck
            ? String(defaultDeck.id)
            : "",
      );
    } catch (error) {
      if (epoch !== statsAccountEpochRef.current) return;
      const failureMessage = getAuthAwareErrorMessage(
        error,
        "덱 목록을 불러오지 못했습니다.",
      );
      setDeckMessage(failureMessage);
      setDeckLoadError(failureMessage);
    } finally {
      if (epoch === statsAccountEpochRef.current) {
        setIsLoadingDecks(false);
      }
    }
  }

  async function loadVocabItems(deckId: string = selectedVocabDeckId) {
    const epoch = statsAccountEpochRef.current;
    setIsLoadingVocab(true);
    setVocabMessage("");

    try {
      const safeDeckId = isSharedDeckStudyId(deckId) ? "all" : deckId;
      const params = new URLSearchParams();
      if (safeDeckId !== "all" && safeDeckId !== "") {
        params.set("deck_id", safeDeckId);
      }
      if (vocabStatusFilter !== "all") {
        params.set("status", vocabStatusFilter);
      }
      const trimmedSearch = vocabSearch.trim();
      if (trimmedSearch) {
        params.set("q", trimmedSearch);
      }
      if (vocabDueOnly) {
        params.set("due_only", "true");
      }
      if (vocabSort) {
        params.set("sort", vocabSort);
      }
      const query = params.toString() ? `?${params.toString()}` : "";
      const data = await requestJson<VocabItemsResponse>(`/vocab-items${query}`);
      if (epoch !== statsAccountEpochRef.current) return;
      setVocabItems(data.items);
    } catch (error) {
      if (epoch !== statsAccountEpochRef.current) return;
      setVocabMessage(
        getAuthAwareErrorMessage(error, "단어장 목록을 불러오지 못했습니다."),
      );
    } finally {
      if (epoch === statsAccountEpochRef.current) {
        setIsLoadingVocab(false);
      }
    }
  }

  // Reading tab: analyzes text with include_known always true so already-known
  // words still render in the natural text flow (just muted), then derives
  // each token's live status from the selected deck's saved vocab items so
  // colors match the deck the user picked. The original text only ever lives
  // in this component's React state (and the local reading session) -- it
  // is never sent anywhere for server-side storage.
  //
  // Long text is split into chunks (splitTextIntoChunks) and each chunk is
  // sent to /analyze one at a time (analyzeLongTextInChunks) -- never all at
  // once -- with results merged back into a single deduped token list in
  // original-text order. For ordinary short text this still runs the same
  // path with exactly one chunk, so nothing changes there.
  async function performReadingAnalyze(analyzeText: string, deckId: string) {
    if (!analyzeText.trim()) {
      setReadingMessage("읽을 일본어 원문을 입력해 주세요.");
      setReadingTokens([]);
      return;
    }
    if (!deckId) {
      setReadingMessage("읽기 덱을 선택해 주세요.");
      return;
    }
    if (isReadingAnalyzing) {
      return;
    }

    const chunks = splitTextIntoChunks(analyzeText);
    if (chunks.length === 0) {
      setReadingMessage("읽을 일본어 원문을 입력해 주세요.");
      setReadingTokens([]);
      return;
    }

    // 새 분석은 이전 작업(상태 저장·일괄 저장·재조회)의 늦은 응답을 무효화한다.
    bumpReadingWork();
    const ctx = captureReadingContext();
    const startToken = getAccessToken();
    setIsReadingAnalyzing(true);
    setReadingMessage("");
    setRecentlySavedVocabItemIds([]);
    setCurrentSelectedTokenKey(null);
    setReadingScrollFraction(null);
    setReadingTabletDocumentScrollFraction(null);
    setIsReadingSessionRestored(false);
    setReadingAnalyzeProgress({ current: 0, total: chunks.length });

    const abortController = new AbortController();
    readingAnalyzeAbortRef.current = abortController;

    try {
      const [outcome, deckVocabResponse] = await Promise.all([
        analyzeLongTextInChunks(
          chunks,
          async (chunkText, signal) => {
            // 각 조각을 보내기 전에: 계정·읽기 세대가 바뀌었거나 토큰이 바뀌었으면
            // 이전 원문을 새 계정 토큰으로 보내지 않고 멈춘다.
            if (!ctx.isCurrent() || getAccessToken() !== startToken) {
              abortController.abort();
              throw new DOMException("reading context changed", "AbortError");
            }
            const response = await apiFetch("/analyze", {
              method: "POST",
              headers: {
                "Content-Type": "application/json",
              },
              body: JSON.stringify({
                text: chunkText,
                deck_id: Number(deckId),
                include_known: true,
              }),
              signal,
            });
            if (!response.ok) {
              throw new Error(`원문을 분석하지 못했어요. (${response.status})`);
            }
            return (await response.json()) as AnalyzeResponse;
          },
          {
            signal: abortController.signal,
            onProgress: (progress) => {
              if (ctx.isCurrent()) setReadingAnalyzeProgress(progress);
            },
          },
        ),
        requestJson<VocabItemsResponse>(`/vocab-items?deck_id=${deckId}`),
      ]);

      if (!ctx.isCurrent()) return;
      if (!ctx.isCurrentForDeck()) {
        setReadingMessage("분석하는 동안 읽기 덱이 바뀌어 결과를 적용하지 않았어요. 다시 분석해 주세요.");
        return;
      }
      if (outcome.cancelled) {
        // A user-initiated cancel mid-analysis shouldn't wipe out whatever
        // reading session (if any) was already on screen before this
        // (re-)analysis started.
        setReadingMessage("분석을 취소했습니다.");
        return;
      }

      const deckItems = deckVocabResponse.items;

      if (outcome.tokens.length === 0 && outcome.failedChunkCount > 0) {
        setReadingMessage(
          `원문을 분석하지 못했어요. 잠시 후 다시 시도해주세요. (${outcome.failedChunkCount}/${outcome.totalChunkCount} 조각 실패)`,
        );
        setReadingTokens([]);
        return;
      }

      const derivedTokens = deriveReadingTokens(outcome.tokens, deckItems, deckId);

      setReadingTokens(derivedTokens);
      setReadingDeckVocabItems(deckItems);
      setAnalyzedReadingText(analyzeText);
      setIsReadingTextCollapsed(true);
      // 새로 분석한 토큰은 지금 계정 덱의 서버 사실에서 다시 계산됐다.
      setReadingDeckConfirmRequired(false);

      if (outcome.failedChunkCount > 0) {
        setReadingMessage(
          `전체 ${outcome.totalChunkCount}조각 중 ${outcome.failedChunkCount}개 구간 분석에 실패했습니다. 나머지는 정상적으로 분석되었습니다. 실패한 구간은 다시 분석해 주세요.`,
        );
      } else if (derivedTokens.length === 0) {
        // Analysis genuinely succeeded but found nothing learnable (e.g. the
        // text is only punctuation/particles) -- without this, the screen
        // would fall back to "덱을 선택하고 원문을 입력한 뒤..." which reads
        // as if analysis never ran at all.
        setReadingMessage(
          "분석했지만 추출된 단어가 없습니다. 다른 일본어 문장으로 다시 시도해보세요.",
        );
      } else if (chunks.length > 1) {
        setReadingMessage(
          `긴 원문을 ${chunks.length}조각으로 나눠 분석을 완료했습니다.`,
        );
      }
    } catch (error) {
      if (!ctx.isCurrent()) return;
      setReadingMessage(
        `원문을 분석하지 못했어요. 잠시 후 다시 시도해주세요. (${getErrorMessage(error, "알 수 없는 문제")})`,
      );
      setReadingTokens([]);
    } finally {
      if (ctx.isCurrent()) {
        setIsReadingAnalyzing(false);
        setReadingAnalyzeProgress(null);
      }
      if (readingAnalyzeAbortRef.current === abortController) {
        readingAnalyzeAbortRef.current = null;
      }
    }
  }

  function handleReadingAnalyze(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    void performReadingAnalyze(readingText, readingSelectedDeckId);
  }

  function cancelReadingAnalyze() {
    readingAnalyzeAbortRef.current?.abort();
  }

  function toggleReadingTextCollapsed() {
    setIsReadingTextCollapsed((collapsed) => !collapsed);
  }

  // Restoring a reading session only brings back the tokens as they were
  // last saved locally; re-fetching the deck's vocab items and re-deriving
  // status/example-sentence from them keeps "already saved" state accurate
  // even if something changed server-side since the last visit.
  async function refreshReadingDeckVocabItems(
    deckId: string,
    baseTokens: TokenWithStatus[],
  ) {
    const ctx = captureReadingContext();
    const seq = readingDeckRequestSeqRef.current.start();
    try {
      const deckVocabResponse = await requestJson<VocabItemsResponse>(
        `/vocab-items?deck_id=${deckId}`,
      );
      if (
        !ctx.isCurrent() ||
        readingSelectedDeckIdRef.current !== deckId ||
        !readingDeckRequestSeqRef.current.isLatest(seq)
      ) {
        return;
      }
      const deckItems = deckVocabResponse.items;
      setReadingDeckVocabItems(deckItems);
      setReadingTokens(deriveReadingTokens(baseTokens, deckItems, deckId));
    } catch {
      // Restored tokens still render fine with their last-known status;
      // this refresh is a nice-to-have, not required for the tab to work.
    }
  }

  // 사용자가 읽기 덱을 바꾸면 이전 덱의 확인·재조회 요청은 무효다(응답은 덱 검사로
  // 버려지고, 그 진행 표시도 여기서 끈다).
  function handleReadingDeckChange(deckId: string) {
    readingDeckRequestSeqRef.current.invalidate();
    setIsReadingDeckConfirmBusy(false);
    setReadingSelectedDeckId(deckId);
  }

  function handleReadingSelectedTokenKeyChange(key: string | null) {
    setCurrentSelectedTokenKey(key);
  }

  function dismissRestoredReadingNotice() {
    setIsReadingSessionRestored(false);
  }

  function resetReadingSession() {
    if (
      !window.confirm(
        "현재 읽기 작업을 초기화할까요? 원문과 분석 결과가 모두 사라집니다.",
      )
    ) {
      return;
    }
    // 이전 분석·상태 저장·일괄 저장·재조회의 늦은 응답이 초기화한 화면을 다시
    // 채우지 않도록 작업을 바꾸고 분석을 멈춘다.
    abortReadingAnalysis();
    bumpReadingGeneration();
    setReadingText("");
    setAnalyzedReadingText("");
    setReadingTokens([]);
    setReadingDeckVocabItems([]);
    setReadingMessage("현재 읽기 작업을 초기화했습니다.");
    setReadingStorageWarning("");
    setIsReadingTextCollapsed(false);
    setRecentlySavedVocabItemIds([]);
    setCurrentSelectedTokenKey(null);
    setReadingScrollFraction(null);
    setReadingTabletDocumentScrollFraction(null);
    setIsReadingSessionRestored(false);
    setReadingDeckConfirmRequired(false);
    readingDataRef.current = { ...emptyReadingData(), deckId: readingSelectedDeckIdRef.current };
    // 삭제는 저장 줄 뒤에 세운다: 이미 예약·진행 중인 저장이 끝난 뒤의 버전으로 지운다.
    const key = readingKeyRef.current;
    if (key) {
      const run = readingSaveChainRef.current.then(() => removeCurrentReadingSession(key));
      readingSaveChainRef.current = run.catch(() => undefined);
    }
  }

  // 사용자가 확인한 초기화: 지금 owner 키 하나만, 이 창이 아는 버전일 때만 지운다.
  async function removeCurrentReadingSession(key: string) {
    const owner = readingOwnerRef.current;
    if (!owner || readingKeyRef.current !== key) return;
    const base = readingBaseRef.current;
    if (!base || readingStorageStatusRef.current !== "ready") {
      if (readingStorageStatusRef.current === "ready") readingPersistedJsonRef.current = null;
      return;
    }
    readingLastAttemptRef.current = { kind: "remove" };
    setReadingLastAttemptKind("remove");
    const sameOwner = () => readingKeyRef.current === key;
    const result = await removeReadingSession(getReadingStorageEnv(), {
      scope: READING_STORAGE_SCOPE,
      owner,
      expected: base,
      isCurrent: sameOwner,
    });
    if (!sameOwner()) return;
    if (result.kind === "ok") {
      readingBaseRef.current = null;
      readingPersistedJsonRef.current = null;
      readingLastAttemptRef.current = null;
    } else if (result.kind === "conflict") {
      setReadingStorage("conflict");
    } else if (result.kind === "unverified") {
      // 지워졌는지 알 수 없다: 자동 저장을 멈추고 재확인·내려받기만 둔다.
      setReadingStorage("unverified");
    } else if (result.kind !== "cancelled") {
      setReadingStorageWarning("이 기기에 저장된 읽기 자료를 지우지 못했어요. 저장된 자료는 그대로 있어요.");
    }
  }

  // Reading tab's own empty-state "샘플 문장으로 체험" button -- only fills
  // the textarea and leaves "분석하기" as the next explicit step (the
  // button only ever renders when the textarea is already empty, so there's
  // nothing to guard against overwriting here).
  function loadSampleReadingText() {
    setReadingText(SAMPLE_TEXT);
    setReadingMessage(
      "샘플 문장을 불러왔습니다. 분석하기를 눌러 단어를 확인해보세요.",
    );
  }

  // Home hero's "샘플로 체험하기" CTA -- jumps to the reading tab with the
  // sample pre-filled and immediately analyzed (reusing the same
  // text+deck -> performReadingAnalyze pipeline the reading tab itself uses), so a first-time visitor sees real token cards
  // without a second click. Guards against silently discarding an
  // in-progress reading session when jumping in from a different tab, the
  // same way resetReadingSession above already confirms before clearing.
  function startSampleReadingFromHome() {
    if (!readingKeyRef.current || readingHydratedKey !== readingKeyRef.current) {
      setActiveTab("reading");
      return;
    }
    const hasExistingReadingWork =
      readingText.trim() !== "" || readingTokens.length > 0;
    if (
      hasExistingReadingWork &&
      !window.confirm(
        "현재 읽기 작업을 샘플 문장으로 바꿀까요? 기존 원문과 분석 결과가 사라집니다.",
      )
    ) {
      return;
    }
    // Clear the previous session's leftover state here rather than relying
    // on performReadingAnalyze's own reset -- that only runs once analysis
    // actually starts, so a still-empty deckId below would otherwise leave
    // a stale CTA/message from the old (possibly days-old, restored)
    // session sitting under the freshly-loaded sample text.
    abortReadingAnalysis();
    bumpReadingWork();
    setRecentlySavedVocabItemIds([]);
    setReadingMessage("");
    setCurrentSelectedTokenKey(null);
    setReadingScrollFraction(null);
    setReadingTabletDocumentScrollFraction(null);
    setIsReadingSessionRestored(false);

    // readingSelectedDeckId may still be empty this early (decks load
    // async on mount) -- fall back to the same default-deck resolution
    // loadDecks() itself seeds that state with, so clicking the sample CTA
    // right after landing on Home still analyzes instead of silently
    // no-op'ing.
    const deckId =
      readingSelectedDeckId || (defaultDeck ? String(defaultDeck.id) : "");
    setReadingText(SAMPLE_TEXT);
    setReadingSelectedDeckId(deckId);
    setActiveTab("reading");
    if (deckId) {
      void performReadingAnalyze(SAMPLE_TEXT, deckId);
    } else {
      setReadingMessage("읽기 덱을 불러온 뒤 다시 시도해주세요.");
    }
  }

  // Reading tab persists status changes immediately (no separate save step)
  // -- except a never-saved word marked known/unclassified, which only
  // updates local reader state (Phase 98): those two statuses aren't a
  // deliberate "save this word" action the way unknown/uncertain are, so a
  // brand-new word shouldn't be written to vocab_items just for being
  // skimmed past. A word that's already saved still gets its status PATCHed
  // regardless of target status -- only the create path is gated.
  async function handleReadingStatusChange(index: number, status: TokenStatus) {
    const token = readingTokens[index];
    if (!token || !readingSelectedDeckId) {
      return;
    }
    if (readingDeckConfirmRequired) {
      setReadingMessage("가져온 분류는 아직 이 계정 단어장과 연결되지 않았어요. 아래 안내에서 덱을 확인해 주세요.");
      return;
    }
    const ctx = captureReadingContext();
    if (token.status === status) {
      return;
    }

    const previousToken = token;

    setReadingTokens((current) =>
      current.map((item, itemIndex) =>
        itemIndex === index ? { ...item, status, isClassified: true } : item,
      ),
    );

    const alreadySavedInDeck = isTokenSavedInDeck(
      token,
      readingDeckVocabItems,
      readingSelectedDeckId,
    );
    if (!alreadySavedInDeck && (status === "known" || status === "unclassified")) {
      return;
    }

    const previousDeckVocabItems = readingDeckVocabItems;

    try {
      const saved = await persistReadingToken(
        token,
        Number(readingSelectedDeckId),
        status,
        readingDeckVocabItems,
      );
      // 이미 서버에 도착한 저장은 되돌리지 않는다. 계정·작업·덱이 바뀌었으면
      // 화면에만 적용하지 않는다.
      if (!ctx.isCurrentForDeck()) return;
      setReadingDeckVocabItems((current) => {
        const exists = current.some((item) => item.id === saved.id);
        return exists
          ? current.map((item) => (item.id === saved.id ? saved : item))
          : [...current, saved];
      });
      setReadingTokens((current) =>
        current.map((item, itemIndex) =>
          itemIndex === index ? applySavedVocabItemToToken(item, saved) : item,
        ),
      );
    } catch (error) {
      if (!ctx.isCurrentForDeck()) return;
      setReadingTokens((current) =>
        current.map((item, itemIndex) =>
          itemIndex === index ? previousToken : item,
        ),
      );
      setReadingDeckVocabItems(previousDeckVocabItems);
      setReadingMessage(
        getErrorMessage(
          error,
          "단어 상태 저장에 실패했습니다. 잠시 후 다시 시도해주세요.",
        ),
      );
    }
  }

  // The one save pipeline every reading save path shares (currently just
  // saveSelectedReadingTokens, driven by the word-list panel's checkbox
  // selection -- Phase 97 removed the other caller, a parallel "save this
  // status bucket immediately" path). Persists a resolved target list via
  // persistReadingToken, merges results back into readingTokens/
  // readingDeckVocabItems, and builds the success/skip/failure summary
  // message. Returns which tokenIndexes actually ended up saved (fresh or
  // already-saved) so a caller like the selective-save flow can react to
  // exactly those (e.g. clear just those from a selection) without guessing
  // from the message string.
  async function persistReadingSaveTargets(
    targets: ReadingSaveTarget[],
    savedCountLabel: string,
  ): Promise<number[]> {
    // Words that are already saved with the exact target status and already
    // have a context sentence need no API call at all -- skip them and
    // report them separately instead of re-sending an unchanged PATCH.
    const toPersist = targets.filter((target) => !target.alreadySaved);
    const skipped = targets.filter((target) => target.alreadySaved);

    const ctx = captureReadingContext();
    const seq = readingBatchSeqRef.current.start();
    setIsSavingReadingBatch(true);
    setReadingMessage("");

    const deckIdNumber = Number(readingSelectedDeckId);
    const results = await Promise.allSettled(
      toPersist.map(({ token, targetStatus }) =>
        persistReadingToken(
          token,
          deckIdNumber,
          targetStatus,
          readingDeckVocabItems,
        ),
      ),
    );

    // 이미 서버에 도착한 저장은 되돌리지 않는다. 계정·작업·덱이 바뀌었거나 더
    // 새 일괄 저장이 있으면 결과를 화면에 적용하지 않는다.
    if (!ctx.isCurrentForDeck() || !readingBatchSeqRef.current.isLatest(seq)) {
      if (readingBatchSeqRef.current.isLatest(seq)) setIsSavingReadingBatch(false);
      return [];
    }
    const succeeded: { index: number; item: VocabItem }[] = [];
    let failureCount = 0;
    results.forEach((result, resultIndex) => {
      if (result.status === "fulfilled") {
        succeeded.push({ index: toPersist[resultIndex].index, item: result.value });
      } else {
        failureCount += 1;
      }
    });

    if (succeeded.length > 0 || skipped.length > 0) {
      const savedItemByIndex = new Map(
        succeeded.map(({ index, item }) => [index, item] as const),
      );
      const skippedItemIdByIndex = new Map(
        skipped.map((target) => [target.index, target.existingItemId] as const),
      );
      setReadingTokens((current) =>
        current.map((item, itemIndex) => {
          const savedItem = savedItemByIndex.get(itemIndex);
          if (savedItem) {
            return applySavedVocabItemToToken(item, savedItem);
          }
          const existingItemId = skippedItemIdByIndex.get(itemIndex);
          if (existingItemId != null) {
            return {
              ...item,
              isClassified: true,
              savedVocabItemId: existingItemId,
            };
          }
          return item;
        }),
      );
      if (succeeded.length > 0) {
        setReadingDeckVocabItems((current) => {
          const byId = new Map(current.map((item) => [item.id, item]));
          succeeded.forEach(({ item }) => byId.set(item.id, item));
          return Array.from(byId.values());
        });
      }
      // "바로 학습"은 방금 새로 저장한 단어뿐 아니라, 이미 저장되어 있어
      // 건너뛴 단어도 이번 텍스트의 학습 대상으로 함께 포함한다.
      const skippedIds = skipped
        .map((target) => target.existingItemId)
        .filter((id): id is number => id !== null);
      setRecentlySavedVocabItemIds([
        ...succeeded.map(({ item }) => item.id),
        ...skippedIds,
      ]);
    }

    setIsSavingReadingBatch(false);
    const parts: string[] = [];
    if (succeeded.length > 0) {
      parts.push(`${savedCountLabel} ${succeeded.length}개를 저장했습니다`);
    }
    if (skipped.length > 0) {
      parts.push(`이미 저장된 단어 ${skipped.length}개는 건너뛰었습니다`);
    }
    if (failureCount > 0) {
      parts.push(`${failureCount}개는 저장하지 못했습니다`);
    }
    if (parts.length === 0) {
      parts.push("저장할 단어가 없습니다");
    }
    // One short closing sentence naming the next step. Deliberately no count
    // here: the "바로 복습" CTA covers newly saved *and* already-saved words
    // (see recentlySavedVocabItemIds above), so quoting this batch's number
    // would contradict the button's own label. Kept free of urgent/time-bound
    // wording because this string is persisted with the reading session and
    // can resurface days later on a restored session.
    const savedAnything = succeeded.length > 0 || skipped.length > 0;
    const nextAction = savedAnything
      ? failureCount > 0
        ? "저장된 단어는 아래 '바로 복습'에서 볼 수 있고, 나머지는 다시 저장할 수 있어요."
        : "아래 '바로 복습'에서 이어서 복습할 수 있어요."
      : failureCount > 0
        ? "다시 저장할 수 있어요."
        : "";
    setReadingMessage(
      `${parts.join(". ")}.${nextAction ? ` ${nextAction}` : ""}`,
    );

    return [
      ...succeeded.map(({ index }) => index),
      ...skipped.map((target) => target.index),
    ];
  }

  // "선택한 단어 저장" -- resolves an explicit set of tokenIndexes the
  // word-list panel's checkboxes (including its quick-select-by-status
  // shortcuts) picked, through the same persist pipeline every reading save
  // path uses. Returns the saved tokenIndexes so the panel can drop exactly
  // those from its selection. Phase 97 removed the only other caller of
  // this pipeline (a parallel "save this status bucket immediately" path,
  // see the ReaderSaveDock note in ReadingTab.tsx), so this is now the sole
  // way reading tokens get saved.
  async function saveSelectedReadingTokens(
    selectedTokenIndexes: number[],
  ): Promise<number[]> {
    if (
      !readingSelectedDeckId ||
      isSavingReadingBatch ||
      selectedTokenIndexes.length === 0
    ) {
      return [];
    }
    if (readingDeckConfirmRequired) {
      setReadingMessage("가져온 분류는 아직 이 계정 단어장과 연결되지 않았어요. 아래 안내에서 덱을 확인해 주세요.");
      return [];
    }

    const targets = resolveSelectedReadingSaveTargets(
      readingTokens,
      readingDeckVocabItems,
      readingSelectedDeckId,
      selectedTokenIndexes,
    );

    if (targets.length === 0) {
      setReadingMessage(
        "선택한 단어 중 저장할 수 있는 단어가 없습니다. 이미 저장한 단어는 어휘 노트에서 볼 수 있어요.",
      );
      return [];
    }

    return persistReadingSaveTargets(targets, "선택한 단어");
  }

  // 저장된 단어로 바로 학습 시작: 학습 탭으로 이동하고 방금 저장한 단어
  // id 목록만 대상으로 하는 "recent" 모드를 자동 시작한다.
  function startStudyFromRecentlySaved() {
    if (recentlySavedVocabItemIds.length === 0) {
      return;
    }
    setActiveTab("study");
    void loadStudyStats(readingSelectedDeckId);
    quickStartStudy("recent", readingSelectedDeckId);
  }

  // 읽기 탭에서 방금 저장한 단어를 단어장 탭에서 바로 확인할 수 있도록
  // 같은 덱을 선택한 채로 이동한다.
  function goToVocabFromReading() {
    setSelectedVocabDeckId(readingSelectedDeckId);
    setActiveTab("vocab");
    void loadVocabItems(readingSelectedDeckId);
    void loadCustomTerms(readingSelectedDeckId);
  }

  async function loadCustomTerms(deckId: string = selectedVocabDeckId) {
    const epoch = statsAccountEpochRef.current;
    try {
      const safeDeckId = isSharedDeckStudyId(deckId) ? "all" : deckId;
      const query =
        safeDeckId !== "all" && safeDeckId !== "" ? `?deck_id=${safeDeckId}` : "";
      const data = await requestJson<CustomTermsResponse>(
        `/custom-terms${query}`,
      );
      if (epoch !== statsAccountEpochRef.current) return;
      setCustomTerms(data.items);
    } catch (error) {
      if (epoch !== statsAccountEpochRef.current) return;
      setVocabMessage(
        getAuthAwareErrorMessage(error, "사용자 정의 용어를 불러오지 못했습니다."),
      );
    }
  }

  async function loadStudyStats(deckId: string = selectedStudyDeckId) {
    const epoch = statsAccountEpochRef.current;
    setIsLoadingStudyStats(true);
    setStudyStatsMessage("");

    try {
      const safeDeckId = isSharedDeckStudyId(deckId) ? "all" : deckId;
      const query =
        safeDeckId !== "all" && safeDeckId !== "" ? `?deck_id=${safeDeckId}` : "";
      const data = await requestJson<StatsResponse>(`/stats${query}`);
      if (epoch !== statsAccountEpochRef.current) return;
      setStudyStats(data);
    } catch (error) {
      if (epoch !== statsAccountEpochRef.current) return;
      setStudyStatsMessage(
        getAuthAwareErrorMessage(error, "학습 통계를 불러오지 못했습니다."),
      );
    } finally {
      if (epoch === statsAccountEpochRef.current) {
        setIsLoadingStudyStats(false);
      }
    }
  }

  async function loadInfoStats() {
    const epoch = statsAccountEpochRef.current;
    setIsLoadingInfoStats(true);
    setInfoStatsMessage("");

    try {
      const data = await requestJson<StatsResponse>("/stats");
      if (epoch === statsAccountEpochRef.current) {
        setInfoStats(data);
      }
    } catch (error) {
      if (epoch === statsAccountEpochRef.current) {
        setInfoStatsMessage(
          getAuthAwareErrorMessage(error, "전체 학습 통계를 불러오지 못했습니다."),
        );
      }
    } finally {
      if (epoch === statsAccountEpochRef.current) {
        setIsLoadingInfoStats(false);
      }
    }
  }

  // Called the moment the account/token changes, before any reload: the
  // previous account's stats and records must not stay on screen.
  // Mid-session token expiry: same account boundary as sign-out -- clear the
  // stats/records first, then fall back to the dev account like the /me
  // check does, and reload the stats data for it.
  // 다른 창에서 로그인·로그아웃·토큰 교체가 일어나면(이 창은 storage 이벤트로
  // 안다) 만료와 같은 경계를 지난다: 이전 내용을 즉시 숨기고 다시 확인한다.
  const handleExternalAuthChangeRef = useRef<() => void>(() => {});
  handleExternalAuthChangeRef.current = () => {
    resetStatsForAccountChange();
    const epoch = statsAccountEpochRef.current;
    setAuthMessage("다른 창에서 계정이 바뀌어 화면을 다시 불러왔어요.");
    void (async () => {
      await loadCurrentUser();
      if (epoch !== statsAccountEpochRef.current) return;
      await refreshUserScopedData();
    })();
  };
  const handleAuthExpiredRef = useRef<() => void>(() => {});
  handleAuthExpiredRef.current = () => {
    // Also clears the expired account's study queue and deck choice (학습 계획
    // Gate D) so the next account can't resume them.
    resetStatsForAccountChange();
    const epoch = statsAccountEpochRef.current;
    setAuthMessage("로그인이 만료되어 로그아웃되었습니다. 다시 로그인해주세요.");
    void (async () => {
      // Stop as soon as a newer sign-in takes over; it reloads for itself.
      // Otherwise reload every account-scoped list the way sign-out does, so
      // decks, words and study numbers of the expired account don't linger.
      await loadCurrentUser();
      if (epoch !== statsAccountEpochRef.current) return;
      await refreshUserScopedData();
    })();
  };
  useEffect(() => {
    const onExpired = () => handleAuthExpiredRef.current();
    window.addEventListener(AUTH_EXPIRED_EVENT, onExpired);
    return () => window.removeEventListener(AUTH_EXPIRED_EVENT, onExpired);
  }, []);

  function resetStatsForAccountChange() {
    statsAccountEpochRef.current += 1;
    planDraftMemoryRef.current.clear();
    setStatsAccountEpoch(statsAccountEpochRef.current);
    setInfoStats(null);
    setInfoStatsMessage("");
    setInfoRecentWords([]);
    setInfoHardWords([]);
    setIsLoadingInfoStats(true);
    setIsLoadingInfoWords(true);
    // Other tabs' account-scoped data. Loaders drop responses from an older
    // epoch, so their loading flags are reset here too.
    setDecks([]);
    setVocabItems([]);
    setCustomTerms([]);
    setStudyStats(null);
    setSelectedSharedDeckId(null);
    setSelectedSharedDeck(null);
    setIsLoadingVocab(false);
    setIsLoadingSharedDeckDetail(false);
    // "" (not "all") -- 단어 탭은 새 계정에서 덱을 고를 때까지 단어를 불러오지
    // 않는다. 복습 세션도 여기서 한 번만 비운다(늦은 갱신이 지우지 않도록).
    setSelectedVocabDeckId("");
    setSelectedStudyDeckId("all");
    resetStudySession();
    // 읽기: 원문·토큰·서버 IDs·선택·위치·안내·진행 상태를 비우고 ReadingTab
    // 자식 상태(바구니·검색·옵션)도 새로 만든다. 다음 owner 확인 뒤 그 키만 연다.
    resetReadingForBoundary();
  }

  // 기록 탭의 "최근 담은 단어" / "자주 틀린 단어" -- 이미 존재하는
  // /vocab-items 정렬 옵션(created_desc/wrong_desc)을 그대로 재사용해 상위
  // 몇 개만 뽑아온다. 실패해도 조용히 빈 목록으로 두고 나머지 기록 화면은
  // 그대로 보여준다 (통계 요약이 이미 핵심 내용이라 이 목록은 보조 정보).
  async function loadInfoWordHighlights() {
    const epoch = statsAccountEpochRef.current;
    setIsLoadingInfoWords(true);
    try {
      const [recentData, hardData] = await Promise.all([
        requestJson<VocabItemsResponse>("/vocab-items?sort=created_desc"),
        requestJson<VocabItemsResponse>("/vocab-items?sort=wrong_desc"),
      ]);
      if (epoch === statsAccountEpochRef.current) {
        setInfoRecentWords(recentData.items.slice(0, 5));
        setInfoHardWords(hardData.items.filter((item) => item.wrong_count > 0).slice(0, 5));
      }
    } catch {
      if (epoch === statsAccountEpochRef.current) {
        setInfoRecentWords([]);
        setInfoHardWords([]);
      }
    } finally {
      if (epoch === statsAccountEpochRef.current) {
        setIsLoadingInfoWords(false);
      }
    }
  }

  // preserveMessage: callers that just wrote a result message (import,
  // unpublish, republish) refresh the list without wiping that message --
  // otherwise React batches the clear with the set and the user never sees it.
  async function loadSharedDecks(options: { preserveMessage?: boolean } = {}) {
    setIsLoadingSharedDecks(true);
    if (!options.preserveMessage) {
      setSharedDeckMessage("");
    }

    const epoch = statsAccountEpochRef.current;
    try {
      const data = await requestJson<SharedDeckSummary[]>("/shared-decks");
      if (epoch !== statsAccountEpochRef.current) return;
      setSharedDecks(data);
      setSharedDecksEpoch(epoch);
      if (
        selectedSharedDeckId !== null &&
        !data.some((deck) => deck.id === selectedSharedDeckId)
      ) {
        setSelectedSharedDeckId(null);
        setSelectedSharedDeck(null);
      }
    } catch (error) {
      if (epoch !== statsAccountEpochRef.current) return;
      setSharedDeckMessage(
        getErrorMessage(
          error,
          "공유덱을 불러오지 못했습니다. 잠시 후 다시 시도해주세요.",
        ),
      );
    } finally {
      if (epoch === statsAccountEpochRef.current) {
        setIsLoadingSharedDecks(false);
      }
    }
  }

  async function loadSharedDeckDetail(sharedDeckId: number) {
    if (selectedSharedDeckId === sharedDeckId && selectedSharedDeck) {
      closeSharedDeckDetail();
      return;
    }
    const epoch = statsAccountEpochRef.current;
    setSelectedSharedDeckId(sharedDeckId);
    setIsLoadingSharedDeckDetail(true);
    setSharedDeckMessage("");

    try {
      const data = await requestJson<SharedDeckDetail>(
        `/shared-decks/${sharedDeckId}`,
      );
      if (epoch !== statsAccountEpochRef.current) return;
      setSelectedSharedDeck(data);
    } catch (error) {
      if (epoch !== statsAccountEpochRef.current) return;
      setSharedDeckMessage(
        getAuthAwareErrorMessage(error, "공유 덱 상세 정보를 불러오지 못했습니다."),
      );
    } finally {
      if (epoch === statsAccountEpochRef.current) {
        setIsLoadingSharedDeckDetail(false);
      }
    }
  }

  function closeSharedDeckDetail() {
    setSelectedSharedDeckId(null);
    setSelectedSharedDeck(null);
    setIsLoadingSharedDeckDetail(false);
  }

  // Best-effort re-fetch of an already-open detail pane's own data (its
  // is_published, is_owner, etc.) after unpublish/republish -- unlike
  // loadSharedDeckDetail() above, this never toggles the pane closed, and a
  // failure here is silent because loadSharedDecks() (called by both
  // callers right before this) already surfaces the authoritative list
  // state and any error message for the action itself.
  async function refreshOpenSharedDeckDetail(sharedDeckId: number) {
    if (selectedSharedDeckId !== sharedDeckId) {
      return;
    }
    try {
      const data = await requestJson<SharedDeckDetail>(
        `/shared-decks/${sharedDeckId}`,
      );
      setSelectedSharedDeck(data);
    } catch {
      // ignore -- see comment above
    }
  }

  function goToVocabTab() {
    setActiveTab("vocab");
    // No specific deck context to hand off here (unlike goToVocabFromReading/
    // goToVocabFromStudy) -- only refresh if the user had already picked a
    // deck previously; otherwise let the 단어 탭's own deck-selection guide
    // show instead of fetching with an empty deck id.
    if (selectedVocabDeckId !== "") {
      void loadVocabItems(selectedVocabDeckId);
      void loadCustomTerms(selectedVocabDeckId);
    }
  }

  async function publishCurrentDeck() {
    if (selectedVocabDeckId === "all" || selectedVocabDeckId === "") {
      setDeckMessage("공유할 덱을 먼저 선택해 주세요.");
      return;
    }

    setIsPublishingDeck(true);
    setDeckMessage("");

    try {
      const result = await requestJson<DeckPublishResponse>(
        `/decks/${selectedVocabDeckId}/publish`,
        {
          method: "POST",
          body: JSON.stringify({
            title: publishTitle,
            description: publishDescription,
          }),
        },
      );
      setPublishTitle("");
      setPublishDescription("");
      setDeckMessage(
        `${result.title} 덱을 공유 덱으로 등록했습니다. 단어 수 ${result.vocab_count}개, 용어 수 ${result.custom_term_count}개가 포함됐어요.`,
      );
      await loadSharedDecks();
    } catch (error) {
      setDeckMessage(getAuthAwareErrorMessage(error, "공유 덱 등록에 실패했습니다."));
    } finally {
      setIsPublishingDeck(false);
    }
  }

  async function importSharedDeckToMyDeck(sharedDeckId: number) {
    if (importingSharedDeckId !== null) {
      return;
    }

    const sourceDeck = sharedDecks.find((deck) => deck.id === sharedDeckId);

    setImportingSharedDeckId(sharedDeckId);
    setImportedSharedDeckId(null);
    setSharedDeckMessage("");

    try {
      const result = await requestJson<SharedDeckImportResponse>(
        `/shared-decks/${sharedDeckId}/import`,
        { method: "POST" },
      );
      const sourceTitle = sourceDeck?.title ?? result.deck_name;
      setImportedSharedDeckId(sharedDeckId);

      if (result.mode === "subscribed") {
        // Lexeme-mode deck: nothing was copied into a personal deck, so
        // there's no vocab_items/decks row to select or load here -- just
        // refresh the shared-deck list so its "가져옴" state updates.
        setSharedDeckMessage(
          `${withObjectParticle(sourceTitle)} 내 학습 목록에 추가했어요.`,
        );
        await loadSharedDecks({ preserveMessage: true });
      } else {
        const totalImportedCount =
          result.imported_vocab_count + result.imported_custom_term_count;
        setSharedDeckMessage(
          `${withObjectParticle(sourceTitle)} 내 어휘 노트에 가져왔어요. 단어 ${totalImportedCount}개를 담았어요.`,
        );
        const importedDeckId = String(result.deck_id);
        setSelectedVocabDeckId(importedDeckId);
        await loadDecks();
        await loadVocabItems(importedDeckId);
        await loadCustomTerms(importedDeckId);
        await loadSharedDecks({ preserveMessage: true });
      }
    } catch (error) {
      setSharedDeckMessage(
        getAuthAwareErrorMessage(
          error,
          "덱을 가져오지 못했어요. 잠시 후 다시 시도해주세요.",
        ),
      );
    } finally {
      setImportingSharedDeckId(null);
    }
  }

  async function unpublishSharedDeck(sharedDeckId: number) {
    if (
      !window.confirm(
        "이 공유덱을 공유 목록에서 내릴까요? 이미 학습 중인 사용자는 계속 복습할 수 있어요.",
      )
    ) {
      return;
    }

    setUnpublishingSharedDeckId(sharedDeckId);
    setSharedDeckMessage("");

    try {
      await requestJson<SharedDeckDeleteResponse>(
        `/shared-decks/${sharedDeckId}`,
        { method: "DELETE" },
      );
      setSharedDeckMessage("공유덱을 공유 목록에서 내렸습니다.");
      // Owner/existing subscribers keep seeing this deck (now unpublished)
      // in their own list/detail -- see docs/architecture/shared-lexeme-progress-storage.md
      // "Owner unpublish policy" -- so re-fetch rather than filtering it out
      // locally, and refresh the open detail pane in place if it's this deck.
      await loadSharedDecks({ preserveMessage: true });
      await refreshOpenSharedDeckDetail(sharedDeckId);
    } catch (error) {
      if (isHttpError(error, 401)) {
        setSharedDeckMessage(
          "로그인 후 사용할 수 있습니다. 저장한 단어와 복습 기록을 이어서 보려면 로그인해주세요.",
        );
      } else if (isHttpError(error, 403)) {
        setSharedDeckMessage("내가 올린 공유덱만 공유 취소할 수 있습니다.");
      } else if (isHttpError(error, 404)) {
        setSharedDeckMessage("이미 삭제되었거나 존재하지 않는 공유덱입니다.");
        await loadSharedDecks({ preserveMessage: true });
      } else {
        setSharedDeckMessage("공유를 취소하지 못했어요. 잠시 후 다시 시도해주세요.");
      }
    } finally {
      setUnpublishingSharedDeckId(null);
    }
  }

  async function republishSharedDeck(sharedDeckId: number) {
    if (
      !window.confirm(
        "이 공유덱을 다시 공유 목록에 올릴까요? 새 사용자도 가져올 수 있게 돼요.",
      )
    ) {
      return;
    }

    setRepublishingSharedDeckId(sharedDeckId);
    setSharedDeckMessage("");

    try {
      const result = await requestJson<SharedDeckRepublishResponse>(
        `/shared-decks/${sharedDeckId}/republish`,
        { method: "POST" },
      );
      setSharedDeckMessage(result.message || "다시 공유했습니다.");
      await loadSharedDecks({ preserveMessage: true });
      await refreshOpenSharedDeckDetail(sharedDeckId);
    } catch (error) {
      if (isHttpError(error, 401)) {
        setSharedDeckMessage(
          "로그인 후 사용할 수 있습니다. 저장한 단어와 복습 기록을 이어서 보려면 로그인해주세요.",
        );
      } else if (isHttpError(error, 403)) {
        setSharedDeckMessage("내가 올린 공유덱만 다시 공유할 수 있습니다.");
      } else if (isHttpError(error, 404)) {
        setSharedDeckMessage("이미 삭제되었거나 존재하지 않는 공유덱입니다.");
        await loadSharedDecks({ preserveMessage: true });
      } else {
        setSharedDeckMessage("다시 공유하지 못했어요. 잠시 후 다시 시도해주세요.");
      }
    } finally {
      setRepublishingSharedDeckId(null);
    }
  }

  // Subscribed shared-deck word status change (see
  // docs/architecture/shared-lexeme-progress-storage.md) -- lexeme_id
  // keyed, lazily creates/updates user_word_progress server-side. Never
  // touches personal vocab_items and never confuses lexeme_id with a
  // vocab_items id.
  async function updateSharedDeckWordStatus(
    sharedDeckId: number,
    lexemeId: number,
    status: TokenStatus,
  ) {
    if (updatingWordLexemeId !== null) {
      return;
    }
    const previousDeck = selectedSharedDeck;
    setUpdatingWordLexemeId(lexemeId);
    // Optimistic update so the dropdown reflects the choice immediately --
    // reverted below if the request actually fails.
    setSelectedSharedDeck((current) => {
      if (!current || current.id !== sharedDeckId) {
        return current;
      }
      return {
        ...current,
        items: current.items.map((item) =>
          item.lexeme_id === lexemeId ? { ...item, status } : item,
        ),
      };
    });

    try {
      await requestJson<LexemeWordProgressResponse>(
        `/shared-decks/${sharedDeckId}/words/${lexemeId}/progress`,
        {
          method: "PATCH",
          body: JSON.stringify({ status }),
        },
      );
    } catch (error) {
      setSelectedSharedDeck(previousDeck);
      setSharedDeckMessage(
        getAuthAwareErrorMessage(
          error,
          "단어 상태를 바꾸지 못했어요. 잠시 후 다시 시도해주세요.",
        ),
      );
    } finally {
      setUpdatingWordLexemeId(null);
    }
  }

  async function createDeck() {
    if (!newDeckName.trim()) {
      setDeckMessage("덱 이름을 입력해 주세요.");
      return;
    }

    setIsCreatingDeck(true);
    setDeckMessage("");

    try {
      const deck = await requestJson<Deck>("/decks", {
        method: "POST",
        body: JSON.stringify({
          name: newDeckName,
          description: newDeckDescription,
        }),
      });
      await loadDecks();
      setSelectedVocabDeckId(String(deck.id));
      setNewDeckName("");
      setNewDeckDescription("");
      setDeckMessage("덱을 저장했습니다.");
    } catch (error) {
      setDeckMessage(getAuthAwareErrorMessage(error, "덱 생성에 실패했습니다."));
    } finally {
      setIsCreatingDeck(false);
    }
  }

  async function deleteDeck(deckId: number) {
    setDeckMessage("");
    if (defaultDeck && deckId === defaultDeck.id) {
      setDeckMessage("기본 단어장은 삭제할 수 없습니다.");
      return;
    }
    if (
      !window.confirm(
        "이 덱을 삭제하면 덱 안의 단어도 모두 삭제됩니다. 계속할까요?",
      )
    ) {
      return;
    }

    try {
      const response = await apiFetch(`/decks/${deckId}`, {
        method: "DELETE",
      });
      if (!response.ok) {
        const data = (await response.json().catch(() => ({}))) as {
          detail?: string;
        };
        throw new Error(data.detail || `덱 삭제에 실패했습니다. (${response.status})`);
      }
      const data = (await response.json()) as DeckDeleteResponse;
      await loadDecks();
      setSelectedVocabDeckId("all");
      if (selectedStudyDeckId === String(deckId)) {
        setSelectedStudyDeckId("all");
      }
      await loadVocabItems("all");
      await loadCustomTerms("all");
      setDeckMessage(
        `덱과 덱에 포함된 단어 ${data.deleted_vocab_count}개를 삭제했습니다.`,
      );
    } catch (error) {
      setDeckMessage(getAuthAwareErrorMessage(error, "덱 삭제에 실패했습니다."));
    }
  }

  async function changeVocabDeck(deckId: string) {
    setSelectedVocabDeckId(deckId);
    // 덱이 바뀌면 이전 덱 기준 검색/필터가 새 덱에 그대로 적용되지 않도록 초기화.
    setVocabSearch("");
    setVocabStatusFilter("all");
    setVocabDueOnly(false);
  }

  function updateNewVocabForm<K extends keyof VocabFormData>(
    field: K,
    value: VocabFormData[K],
  ) {
    setNewVocabForm((currentForm) => ({
      ...currentForm,
      [field]: value,
    }));
  }

  function updateEditVocabForm<K extends keyof VocabFormData>(
    field: K,
    value: VocabFormData[K],
  ) {
    setEditVocabForm((currentForm) => ({
      ...currentForm,
      [field]: value,
    }));
  }

  function updateNewCustomTermForm<K extends keyof CustomTermFormData>(
    field: K,
    value: CustomTermFormData[K],
  ) {
    setNewCustomTermForm((currentForm) => ({
      ...currentForm,
      [field]: value,
    }));
  }

  function updateEditCustomTermForm<K extends keyof CustomTermFormData>(
    field: K,
    value: CustomTermFormData[K],
  ) {
    setEditCustomTermForm((currentForm) => ({
      ...currentForm,
      [field]: value,
    }));
  }

  function buildCustomTermPayload(form: CustomTermFormData) {
    return {
      term: form.term,
      reading: form.reading,
      part_of_speech: form.part_of_speech,
      meaning_ko: form.meaning_ko,
      description: form.description,
      deck_id: form.deck_id ? Number(form.deck_id) : null,
    };
  }

  function buildVocabPayload(form: VocabFormData) {
    return {
      surface: form.surface,
      base_form: form.base_form,
      reading: form.reading,
      part_of_speech: form.part_of_speech,
      meaning_ko: form.meaning_ko,
      dictionary_gloss: form.dictionary_gloss,
      quality_tag: form.quality_tag,
      context_explanation_ko: form.context_explanation_ko,
      example_sentence: form.example_sentence,
      status: form.status,
      deck_id: form.deck_id ? Number(form.deck_id) : null,
    };
  }

  async function addVocabItem() {
    if (!newVocabForm.surface.trim() && !newVocabForm.base_form.trim()) {
      setVocabMessage("단어 또는 기본형을 입력해 주세요.");
      return;
    }

    setIsAddingVocab(true);
    setVocabMessage("");

    try {
      await requestJson<VocabItem>("/vocab-items", {
        method: "POST",
        body: JSON.stringify(buildVocabPayload(newVocabForm)),
      });
      setNewVocabForm(createBlankVocabForm(defaultVocabFormDeckId));
      setIsNewVocabFormOpen(false);
      setVocabMessage("단어를 저장했습니다.");
      await loadVocabItems();
    } catch (error) {
      setVocabMessage(getAuthAwareErrorMessage(error, "단어 추가에 실패했습니다."));
    } finally {
      setIsAddingVocab(false);
    }
  }

  async function addCustomTerm() {
    if (!newCustomTermForm.term.trim()) {
      setVocabMessage("사용자 정의 용어를 입력해 주세요.");
      return;
    }

    setIsSavingCustomTerm(true);
    setVocabMessage("");

    try {
      await requestJson<CustomTerm>("/custom-terms", {
        method: "POST",
        body: JSON.stringify(buildCustomTermPayload(newCustomTermForm)),
      });
      setNewCustomTermForm(
        createBlankCustomTermForm(
          selectedVocabDeckId !== "all" ? selectedVocabDeckId : "",
        ),
      );
      setIsCustomTermFormOpen(false);
      setVocabMessage("사용자 정의 용어를 저장했습니다.");
      await loadCustomTerms();
    } catch (error) {
      setVocabMessage(
        getAuthAwareErrorMessage(error, "사용자 정의 용어 추가에 실패했습니다."),
      );
    } finally {
      setIsSavingCustomTerm(false);
    }
  }

  function startEditingCustomTerm(term: CustomTerm) {
    setEditingCustomTermId(term.id);
    setEditCustomTermForm(customTermToForm(term));
    setVocabMessage("");
  }

  function cancelEditingCustomTerm() {
    setEditingCustomTermId(null);
    setEditCustomTermForm(createBlankCustomTermForm());
  }

  async function saveEditedCustomTerm() {
    if (editingCustomTermId === null) {
      return;
    }
    if (!editCustomTermForm.term.trim()) {
      setVocabMessage("사용자 정의 용어를 입력해 주세요.");
      return;
    }

    setIsSavingCustomTerm(true);
    setVocabMessage("");

    try {
      await requestJson<CustomTerm>(`/custom-terms/${editingCustomTermId}`, {
        method: "PATCH",
        body: JSON.stringify(buildCustomTermPayload(editCustomTermForm)),
      });
      setEditingCustomTermId(null);
      setVocabMessage("사용자 정의 용어를 수정했습니다.");
      await loadCustomTerms();
    } catch (error) {
      setVocabMessage(
        getAuthAwareErrorMessage(error, "사용자 정의 용어 수정에 실패했습니다."),
      );
    } finally {
      setIsSavingCustomTerm(false);
    }
  }

  async function deleteCustomTerm(termId: number) {
    setVocabMessage("");

    try {
      const response = await apiFetch(`/custom-terms/${termId}`, {
        method: "DELETE",
      });
      if (!response.ok) {
        throw new Error(`사용자 정의 용어 삭제에 실패했습니다. (${response.status})`);
      }
      setVocabMessage("사용자 정의 용어를 삭제했습니다.");
      await loadCustomTerms();
    } catch (error) {
      setVocabMessage(
        getAuthAwareErrorMessage(error, "사용자 정의 용어 삭제에 실패했습니다."),
      );
    }
  }

  function startEditingVocabItem(item: VocabItem) {
    setEditingItemId(item.id);
    setEditVocabForm(vocabItemToForm(item));
    setVocabMessage("");
  }

  function cancelEditingVocabItem() {
    setEditingItemId(null);
    setEditVocabForm(createBlankVocabForm(defaultVocabFormDeckId));
  }

  async function saveEditedVocabItem() {
    if (editingItemId === null) {
      return;
    }
    if (!editVocabForm.surface.trim() && !editVocabForm.base_form.trim()) {
      setVocabMessage("단어 또는 기본형을 입력해 주세요.");
      return;
    }

    setIsUpdatingVocab(true);
    setVocabMessage("");

    try {
      await requestJson<VocabItem>(`/vocab-items/${editingItemId}`, {
        method: "PATCH",
        body: JSON.stringify(buildVocabPayload(editVocabForm)),
      });
      setEditingItemId(null);
      setVocabMessage("단어를 수정했습니다.");
      await loadVocabItems();
    } catch (error) {
      setVocabMessage(getAuthAwareErrorMessage(error, "단어 수정에 실패했습니다."));
    } finally {
      setIsUpdatingVocab(false);
    }
  }

  function startMeaningEdit(itemId: number, currentMeaning: string) {
    setMeaningEditItemId(itemId);
    setMeaningEditDraft(currentMeaning);
    setMeaningEditMessage("");
  }

  function cancelMeaningEdit() {
    setMeaningEditItemId(null);
    setMeaningEditDraft("");
    setMeaningEditMessage("");
  }

  // Applies a fresh meaning_ko everywhere this vocab item might already be
  // cached across tabs, so the edit shows up immediately without needing a
  // full reload of each tab's own data.
  function applyUpdatedVocabItemEverywhere(
    updated: VocabItem,
    options: { includeReading?: boolean } = {},
  ) {
    const includeReading = options.includeReading ?? true;
    const replaceIfMatch = (item: VocabItem) =>
      item.id === updated.id ? updated : item;
    setVocabItems((current) => current.map(replaceIfMatch));
    setReadingDeckVocabItems((current) => current.map(replaceIfMatch));
    // studyItems mixes in lexeme study cards (item_type: "lexeme") alongside
    // vocab ones -- only re-tag the matching *vocab* card, and keep it as a
    // StudyCardItem rather than collapsing it back down to a bare VocabItem.
    setStudyItems((current) =>
      current.map((item) =>
        item.item_type === "vocab" && item.id === updated.id
          ? toVocabStudyCardItem(updated)
          : item,
      ),
    );
    if (!includeReading) return;
    setReadingTokens((current) =>
      current.map((token) =>
        token.savedVocabItemId === updated.id
          ? { ...token, savedMeaningKo: updated.meaning_ko }
          : token,
      ),
    );
  }

  async function saveMeaningEdit() {
    if (meaningEditItemId === null || isSavingMeaningEdit) {
      return;
    }
    const trimmed = meaningEditDraft.trim();
    if (!trimmed) {
      setMeaningEditMessage("뜻을 입력해 주세요.");
      return;
    }
    if (trimmed.length > MAX_MEANING_KO_LENGTH) {
      setMeaningEditMessage(`뜻은 ${MAX_MEANING_KO_LENGTH}자 이내로 입력해 주세요.`);
      return;
    }

    const epoch = statsAccountEpochRef.current;
    const readingCtx = captureReadingContext();
    const editedItemId = meaningEditItemId;
    const seq = meaningEditSeqRef.current.start();
    // 같은 편집 창(같은 항목)의 마지막 요청일 때만 편집 창 상태를 바꾼다.
    const isSameEdit = () =>
      meaningEditSeqRef.current.isLatest(seq) && meaningEditItemIdRef.current === editedItemId;
    setIsSavingMeaningEdit(true);
    setMeaningEditMessage("");

    try {
      const updated = await requestJson<VocabItem>(
        `/vocab-items/${meaningEditItemId}`,
        {
          method: "PATCH",
          body: JSON.stringify({ meaning_ko: trimmed }),
        },
      );
      if (epoch !== statsAccountEpochRef.current) return;
      // 서버 항목은 같은 계정의 사실이므로 목록에는 반영하되, 읽기 작업이
      // 바뀌었으면 새 작업의 토큰은 건드리지 않는다.
      applyUpdatedVocabItemEverywhere(updated, { includeReading: readingCtx.isCurrent() });
      if (!isSameEdit()) return;
      setMeaningEditItemId(null);
      setMeaningEditDraft("");
      setMeaningEditMessage("");
    } catch (error) {
      if (epoch !== statsAccountEpochRef.current || !isSameEdit()) return;
      setMeaningEditMessage(getAuthAwareErrorMessage(error, "뜻 수정에 실패했습니다."));
    } finally {
      if (epoch === statsAccountEpochRef.current && meaningEditSeqRef.current.isLatest(seq)) {
        setIsSavingMeaningEdit(false);
      }
    }
  }

  function openMeaningFeedback(target: MeaningFeedbackTarget) {
    setMeaningFeedbackTarget(target);
    setFeedbackSuggestedMeaning("");
    setFeedbackReason("");
    setFeedbackMessage("");
  }

  function closeMeaningFeedback() {
    setMeaningFeedbackTarget(null);
  }

  async function submitMeaningFeedback() {
    if (!meaningFeedbackTarget || isSubmittingFeedback) {
      return;
    }

    const epoch = statsAccountEpochRef.current;
    const target = meaningFeedbackTarget;
    const seq = feedbackSeqRef.current.start();
    // 같은 신고 창의 마지막 요청일 때만 그 창의 안내를 바꾼다.
    const isSameReport = () =>
      epoch === statsAccountEpochRef.current &&
      feedbackSeqRef.current.isLatest(seq) &&
      meaningFeedbackTargetRef.current === target;
    setIsSubmittingFeedback(true);
    setFeedbackMessage("");

    try {
      await requestJson("/feedback/meaning", {
        method: "POST",
        body: JSON.stringify({
          vocabulary_id: meaningFeedbackTarget.vocabularyId,
          surface: meaningFeedbackTarget.surface,
          base_form: meaningFeedbackTarget.baseForm,
          reading: meaningFeedbackTarget.reading,
          current_meaning_ko: meaningFeedbackTarget.currentMeaningKo,
          suggested_meaning_ko: feedbackSuggestedMeaning.trim(),
          reason: feedbackReason.trim(),
          source: meaningFeedbackTarget.source,
        }),
      });
      if (!isSameReport()) return;
      setFeedbackMessage("신고를 보냈어요. 사전 품질 개선에 참고할게요.");
    } catch (error) {
      if (!isSameReport()) return;
      setFeedbackMessage(getAuthAwareErrorMessage(error, "신고 접수에 실패했습니다."));
    } finally {
      if (epoch === statsAccountEpochRef.current && feedbackSeqRef.current.isLatest(seq)) {
        setIsSubmittingFeedback(false);
      }
    }
  }

  function openAppFeedback() {
    setIsAppFeedbackOpen(true);
    setAppFeedbackCategory("ux");
    setAppFeedbackDraft("");
    setAppFeedbackResultMessage("");
  }

  function closeAppFeedback() {
    setIsAppFeedbackOpen(false);
  }

  async function submitAppFeedback() {
    const message = appFeedbackDraft.trim();
    if (message.length < 10 || isSubmittingAppFeedback) {
      return;
    }

    setIsSubmittingAppFeedback(true);
    setAppFeedbackResultMessage("");

    try {
      await requestJson("/feedback/app", {
        method: "POST",
        body: JSON.stringify({
          category: appFeedbackCategory,
          message,
          // Only the current tab name -- never the reading-tab's original
          // text/localStorage session content.
          screen: activeTab,
          path: `/${activeTab}`,
        }),
      });
      setAppFeedbackDraft("");
      setAppFeedbackResultMessage("피드백을 보냈어요. 베타 개선에 반영할게요.");
    } catch (error) {
      setAppFeedbackResultMessage(
        getAuthAwareErrorMessage(error, "피드백을 보내지 못했습니다. 잠시 후 다시 시도해주세요."),
      );
    } finally {
      setIsSubmittingAppFeedback(false);
    }
  }

  async function updateVocabStatus(itemId: number, status: TokenStatus) {
    const previousItems = vocabItems;
    setVocabItems((currentItems) =>
      currentItems.map((item) =>
        item.id === itemId ? { ...item, status } : item,
      ),
    );
    setVocabMessage("");

    try {
      await requestJson<VocabItem>(`/vocab-items/${itemId}`, {
        method: "PATCH",
        body: JSON.stringify({ status }),
      });
      await loadVocabItems();
    } catch (error) {
      setVocabItems(previousItems);
      setVocabMessage(getAuthAwareErrorMessage(error, "상태 변경에 실패했습니다."));
    }
  }

  async function deleteVocabItem(itemId: number) {
    const previousItems = vocabItems;
    setVocabItems((currentItems) =>
      currentItems.filter((item) => item.id !== itemId),
    );
    setVocabMessage("");

    try {
      const response = await apiFetch(`/vocab-items/${itemId}`, {
        method: "DELETE",
      });
      if (!response.ok) {
        throw new Error(`삭제에 실패했습니다. (${response.status})`);
      }
      await loadVocabItems();
    } catch (error) {
      setVocabItems(previousItems);
      setVocabMessage(getAuthAwareErrorMessage(error, "삭제에 실패했습니다."));
    }
  }

  function createDeckPackageFilename(deckName: string) {
    const slug =
      deckName
        .trim()
        .toLowerCase()
        .replace(/[\\/:*?"<>|]+/g, "_")
        .replace(/\s+/g, "_")
        .replace(/^_+|_+$/g, "")
        .slice(0, 48) || "deck";
    const date = new Date().toISOString().slice(0, 10);
    return `jp_vocab_deck_${slug}_${date}.json`;
  }

  async function exportDeckPackage() {
    if (selectedVocabDeckId === "all" || selectedVocabDeckId === "") {
      setVocabMessage("공유 파일로 내보낼 덱을 먼저 선택해 주세요.");
      return;
    }

    setIsExportingDeckPackage(true);
    setVocabMessage("덱 공유 파일을 준비하고 있습니다.");

    try {
      const packageData = await requestJson<{
        deck: { name: string };
      }>(`/decks/${selectedVocabDeckId}/export-package`);
      const blob = new Blob([JSON.stringify(packageData, null, 2)], {
        type: "application/json;charset=utf-8",
      });
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = createDeckPackageFilename(packageData.deck.name);
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(url);
      setVocabMessage("덱 공유 파일 다운로드를 시작했습니다.");
    } catch (error) {
      setVocabMessage(
        getAuthAwareErrorMessage(error, "덱 공유 파일 내보내기에 실패했습니다."),
      );
    } finally {
      setIsExportingDeckPackage(false);
    }
  }

  async function importDeckPackage() {
    if (!deckPackageFile) {
      setVocabMessage("가져올 덱 공유 JSON 파일을 선택해 주세요.");
      return;
    }

    setIsImportingDeckPackage(true);
    setVocabMessage("덱 공유 파일을 가져오고 있습니다.");

    try {
      let packageData: unknown;
      try {
        packageData = JSON.parse(await deckPackageFile.text());
      } catch {
        throw new Error("올바른 JSON 파일이 아닙니다.");
      }

      const result = await requestJson<DeckPackageImportResponse>(
        "/decks/import-package",
        {
          method: "POST",
          body: JSON.stringify(packageData),
        },
      );
      setDeckPackageFile(null);
      await loadDecks();
      setSelectedVocabDeckId(String(result.deck_id));
      await loadVocabItems(String(result.deck_id));
      await loadCustomTerms(String(result.deck_id));
      setVocabMessage(
        `${result.deck_name} 덱을 만들고 단어 ${result.imported_vocab_count}개, 사용자 용어 ${result.imported_custom_term_count}개를 가져왔습니다.`,
      );
    } catch (error) {
      setVocabMessage(
        getAuthAwareErrorMessage(error, "덱 공유 파일 가져오기에 실패했습니다."),
      );
    } finally {
      setIsImportingDeckPackage(false);
    }
  }

  async function downloadCsv() {
    setIsExportingCsv(true);
    setVocabMessage("CSV 파일을 준비하고 있습니다.");

    try {
      const query =
        selectedVocabDeckId !== "all" && selectedVocabDeckId !== ""
          ? `?deck_id=${selectedVocabDeckId}`
          : "";
      const response = await apiFetch(`/vocab-items/export.csv${query}`);
      if (!response.ok) {
        throw new Error(`CSV 다운로드에 실패했습니다. (${response.status})`);
      }

      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = "jp-vocab-items.csv";
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(url);
      setVocabMessage("CSV 다운로드를 시작했습니다.");
    } catch (error) {
      setVocabMessage(getAuthAwareErrorMessage(error, "CSV 다운로드에 실패했습니다."));
    } finally {
      setIsExportingCsv(false);
    }
  }

  function getDeckDisplayName(deckId: string) {
    if (deckId === "all") {
      return "전체 단어장";
    }
    if (deckId.startsWith(SHARED_DECK_STUDY_ID_PREFIX)) {
      const sharedDeckId = Number(deckId.slice(SHARED_DECK_STUDY_ID_PREFIX.length));
      return (
        sharedDecks.find((deck) => deck.id === sharedDeckId)?.title ?? "가져온 덱"
      );
    }
    return decks.find((deck) => String(deck.id) === deckId)?.name ?? "선택한 덱";
  }

  // Phase 3 (see docs/architecture/shared-lexeme-progress-storage.md -- "SRS
  // card integration"): tag a plain vocab item / lexeme study item with the
  // common item_type-discriminated shape the study card renders. A lexeme
  // item's synthetic `id` is always negative -- vocab_item ids are positive
  // DB autoincrement ids, so this can never collide, and lexeme_id/
  // shared_deck_id (not `id`) are what rating submission actually keys off.
  function toVocabStudyCardItem(item: VocabItem): StudyCardItem {
    return {
      ...item,
      item_type: "vocab",
      vocab_item_id: item.id,
      lexeme_id: null,
      shared_deck_id: null,
      source_label: item.deck_name || "내 단어장",
    };
  }

  function toLexemeStudyCardItem(item: StudyLexemeItem): StudyCardItem {
    return {
      id: -item.lexeme_id,
      deck_id: item.shared_deck_id,
      deck_name: item.source_label,
      surface: item.surface,
      base_form: item.base_form,
      reading: item.reading,
      part_of_speech: item.part_of_speech,
      normalized_form: item.base_form,
      meaning_ko: item.meaning_ko,
      dictionary_gloss: item.dictionary_gloss ?? "",
      quality_tag: "normal",
      example_sentence: item.example_sentence ?? "",
      is_custom_term: false,
      occurrence_count: 1,
      jlpt_level: item.jlpt_level,
      status: item.status,
      context_explanation_ko: item.context_explanation_ko ?? "",
      correct_count: item.correct_count,
      wrong_count: item.wrong_count,
      last_reviewed_at: null,
      review_level: item.review_level,
      next_review_at: item.next_review_at,
      created_at: "",
      updated_at: "",
      item_type: "lexeme",
      vocab_item_id: null,
      lexeme_id: item.lexeme_id,
      shared_deck_id: item.shared_deck_id,
      source_label: item.source_label,
    };
  }

  async function fetchLexemeStudyItems(
    options: {
      sharedDeckId?: number;
      dueOnly?: boolean;
      limit?: number;
      // 학습 계획 첫 학습 큐: 서버가 미평가 단어만 고른 뒤 LIMIT (known 제외 없음).
      firstReviewOnly?: boolean;
    } = {},
  ) {
    const params = new URLSearchParams();
    if (options.sharedDeckId !== undefined) {
      params.set("shared_deck_id", String(options.sharedDeckId));
    }
    if (options.dueOnly) {
      params.set("due_only", "true");
    }
    if (options.firstReviewOnly) {
      params.set("first_review_only", "true");
    }
    if (options.limit !== undefined) {
      params.set("limit", String(options.limit));
    }
    const query = params.toString() ? `?${params.toString()}` : "";
    return requestJson<StudyLexemeItem[]>(`/study-items/lexemes${query}`);
  }

  async function fetchStudyItems(deckId: string, mode: StudyMode) {
    // A subscribed shared deck was picked in the deck selector -- study only
    // that deck's lexeme words, no personal vocab_items mixed in. "recent"
    // (방금 담은 단어) is a personal-vocab-only concept, so it stays empty here.
    if (deckId.startsWith(SHARED_DECK_STUDY_ID_PREFIX)) {
      if (mode === "recent") {
        return [];
      }
      const sharedDeckId = Number(deckId.slice(SHARED_DECK_STUDY_ID_PREFIX.length));
      if (mode === "new") {
        const newLexemeItems = await fetchLexemeStudyItems({
          sharedDeckId,
          limit: NEW_LEXEME_STUDY_LIMIT,
        });
        return newLexemeItems
          .filter((item) => item.status === "unclassified")
          .map(toLexemeStudyCardItem);
      }
      const lexemeItems = await fetchLexemeStudyItems({
        sharedDeckId,
        dueOnly: mode === "today",
      });
      let filtered = lexemeItems;
      if (mode === "uncertain") {
        filtered = lexemeItems.filter((item) => item.status === "uncertain");
      } else if (mode === "unknown") {
        filtered = lexemeItems.filter(
          (item) => item.status === "unknown" || item.status === "unclassified",
        );
      }
      return filtered.map(toLexemeStudyCardItem);
    }

    const baseParams = new URLSearchParams();
    if (deckId !== "all") {
      baseParams.set("deck_id", deckId);
    }

    if (mode === "today") {
      const query = baseParams.toString() ? `?${baseParams.toString()}` : "";
      const data = await requestJson<StudyItemsResponse>(`/study-items${query}`);
      const vocabCards = data.items.map(toVocabStudyCardItem);
      // Only merge in subscribed-deck lexeme words for the "everything"
      // view (no specific personal deck selected) -- a specific personal
      // deck's study session should stay scoped to that deck's own words.
      if (deckId !== "all") {
        return vocabCards;
      }
      const lexemeItems = await fetchLexemeStudyItems({ dueOnly: true });
      return [...vocabCards, ...lexemeItems.map(toLexemeStudyCardItem)];
    }

    if (mode === "all") {
      const fetchByStatus = async (status: "unknown" | "uncertain") => {
        const params = new URLSearchParams(baseParams);
        params.set("status", status);
        params.set("sort", "next_review_asc");
        const data = await requestJson<VocabItemsResponse>(
          `/vocab-items?${params.toString()}`,
        );
        return data.items;
      };
      const [unknownItems, uncertainItems] = await Promise.all([
        fetchByStatus("unknown"),
        fetchByStatus("uncertain"),
      ]);
      return [...unknownItems, ...uncertainItems].map(toVocabStudyCardItem);
    }

    if (mode === "new") {
      const params = new URLSearchParams(baseParams);
      params.set("sort", "created_asc");
      const data = await requestJson<VocabItemsResponse>(
        `/vocab-items?${params.toString()}`,
      );
      const vocabCards = data.items
        .filter((item) => !item.last_reviewed_at)
        .map(toVocabStudyCardItem);
      if (deckId !== "all") {
        return vocabCards;
      }
      const lexemeItems = await fetchLexemeStudyItems({ limit: NEW_LEXEME_STUDY_LIMIT });
      const newLexemeCards = lexemeItems
        .filter((item) => item.status === "unclassified")
        .map(toLexemeStudyCardItem);
      return [...vocabCards, ...newLexemeCards];
    }

    if (mode === "recent") {
      if (recentlySavedVocabItemIds.length === 0) {
        return [];
      }
      const data = await requestJson<VocabItemsResponse>(
        `/vocab-items?${baseParams.toString()}`,
      );
      const recentIds = new Set(recentlySavedVocabItemIds);
      return data.items.filter((item) => recentIds.has(item.id)).map(toVocabStudyCardItem);
    }

    const params = new URLSearchParams(baseParams);
    params.set("status", mode);
    params.set("sort", "next_review_asc");
    const data = await requestJson<VocabItemsResponse>(
      `/vocab-items?${params.toString()}`,
    );
    return data.items.map(toVocabStudyCardItem);
  }

  function getEmptyStudyMessage(mode: StudyMode, deckId: string) {
    const deckName = getDeckDisplayName(deckId);
    if (mode === "today") {
      return `${deckName}에는 오늘 복습할 단어가 없어요.`;
    }
    if (mode === "uncertain") {
      return `${deckName}에 헷갈리는 단어가 없어요.`;
    }
    if (mode === "unknown") {
      return `${deckName}에 모르는 단어가 없어요.`;
    }
    if (mode === "new") {
      return "새로 학습할 단어가 없어요.";
    }
    if (mode === "recent") {
      return "방금 담은 단어를 찾을 수 없어요.";
    }
    return `${deckName}에 학습할 모르는 단어와 헷갈리는 단어가 없어요.`;
  }

  async function startStudy(
    options: { deckId?: string; mode?: StudyMode } = {},
  ) {
    const deckId = options.deckId ?? selectedStudyDeckId;
    const mode = options.mode ?? studyMode;
    studySessionIdRef.current += 1;
    // A newer session (or an account change, which resets the session) makes
    // this fetch's result stale.
    const sessionId = studySessionIdRef.current;
    const epoch = statsAccountEpochRef.current;
    const isCurrent = () =>
      sessionId === studySessionIdRef.current && epoch === statsAccountEpochRef.current;
    setIsLoadingStudy(true);
    setStudyMessage("");
    setStudyItems([]);
    setCurrentStudyIndex(0);
    setIsAnswerVisible(false);
    setSessionCounts(createEmptySessionCounts());
    setNextUpcomingReviewAt(null);
    setAgainNextReviewAt(null);
    answerShownAtRef.current = null;
    setHasStartedStudy(false);

    try {
      const items = await fetchStudyItems(deckId, mode);
      if (!isCurrent()) return;
      setStudyItems(items);
      setHasStartedStudy(true);
      if (items.length === 0) {
        setStudyMessage(getEmptyStudyMessage(mode, deckId));
      }
    } catch (error) {
      if (!isCurrent()) return;
      setStudyMessage(
        getAuthAwareErrorMessage(error, "학습 대상 단어를 불러오지 못했습니다."),
      );
    } finally {
      if (isCurrent()) {
        setIsLoadingStudy(false);
      }
    }
  }

  // ---- 학습 계획 → 복습 탭 실행 (Gate C-1b) ----
  // LearningPlanPanel(studyLauncher prop)에 넘길 실행기. 화면 노출과 메뉴
  // 연결은 Gate D. 하루량으로 큐를 자르지 않는다: 개인 new는 기존 new 모드
  // 그대로(미평가 카드 전부), 구독 new는 서버 first_review_only 큐(기존
  // NEW_LEXEME_STUDY_LIMIT), today는 기존 today 모드 그대로다.
  async function fetchPlanStudyQueue(target: PlanStudyTarget): Promise<StudyCardItem[]> {
    if (target.deck.kind === "personal") {
      return fetchStudyItems(String(target.deck.id), target.mode);
    }
    if (target.mode === "new") {
      const items = await fetchLexemeStudyItems({
        sharedDeckId: target.deck.id,
        firstReviewOnly: true,
        limit: NEW_LEXEME_STUDY_LIMIT,
      });
      // 상태값으로 다시 거르지 않는다: 첫 학습 여부는 서버가 last_reviewed_at으로 판단.
      return items.map(toLexemeStudyCardItem);
    }
    return fetchStudyItems(`${SHARED_DECK_STUDY_ID_PREFIX}${target.deck.id}`, "today");
  }

  function replaceStudySessionFromPlan(target: PlanStudyTarget, items: StudyCardItem[]) {
    const deckId =
      target.deck.kind === "personal"
        ? String(target.deck.id)
        : `${SHARED_DECK_STUDY_ID_PREFIX}${target.deck.id}`;
    studySessionIdRef.current += 1;
    setIsLoadingStudy(false);
    setSelectedStudyDeckId(deckId);
    setStudyMode(target.mode);
    setStudyItems(items);
    setCurrentStudyIndex(0);
    setIsAnswerVisible(false);
    setSessionCounts(createEmptySessionCounts());
    setNextUpcomingReviewAt(null);
    setAgainNextReviewAt(null);
    answerShownAtRef.current = null;
    setStudyMessage("");
    setHasStartedStudy(true);
    setActiveTab("study");
    void loadStudyStats(deckId);
  }

  // 실행기는 비동기 조회 뒤에 "지금" 세션을 다시 확인해야 하므로 최신 상태를
  // ref로 읽는다(렌더마다 갱신).
  const planStudyStateRef = useRef({ studyItems, currentStudyIndex, hasStartedStudy });
  planStudyStateRef.current = { studyItems, currentStudyIndex, hasStartedStudy };
  const planStudyActionsRef = useRef({ fetchPlanStudyQueue, replaceStudySessionFromPlan });
  planStudyActionsRef.current = { fetchPlanStudyQueue, replaceStudySessionFromPlan };
  const planStudyLauncherRef = useRef<PlanStudyLauncher | null>(null);
  if (!planStudyLauncherRef.current) {
    planStudyLauncherRef.current = createPlanStudyLauncher<StudyCardItem>({
      getSession: (): StudySessionSnapshot => {
        const { studyItems: items, currentStudyIndex: index, hasStartedStudy: started } =
          planStudyStateRef.current;
        const remaining = started ? Math.max(items.length - index, 0) : 0;
        return {
          id: studySessionIdRef.current,
          position: index,
          inProgress: remaining > 0,
          remaining,
        };
      },
      getAccountEpoch: () => statsAccountEpochRef.current,
      fetchQueue: (target) => planStudyActionsRef.current.fetchPlanStudyQueue(target),
      replaceSession: (target, items) =>
        planStudyActionsRef.current.replaceStudySessionFromPlan(target, items),
      resumeSession: () => setActiveTab("study"),
    });
  }

  function changeStudyMode(mode: StudyMode) {
    setStudyMode(mode);
    if (hasStartedStudy) {
      void startStudy({ mode });
    } else {
      resetStudySession();
    }
  }

  function quickStartStudy(mode: StudyMode, deckId?: string) {
    setStudyMode(mode);
    if (deckId !== undefined) {
      setSelectedStudyDeckId(deckId);
    }
    // Pass deckId through explicitly rather than relying on
    // selectedStudyDeckId state -- setSelectedStudyDeckId above hasn't
    // committed yet by the time startStudy's closure would read it.
    void startStudy({ mode, deckId });
  }

  function changeStudyDeck(deckId: string) {
    setSelectedStudyDeckId(deckId);
    void loadStudyStats(deckId);
    if (hasStartedStudy) {
      void startStudy({ deckId });
    } else {
      resetStudySession();
    }
  }

  function startStudyFromVocabDeck() {
    if (selectedVocabDeckId === "all" || selectedVocabDeckId === "") {
      setVocabMessage("학습할 특정 덱을 먼저 선택해 주세요.");
      return;
    }
    setSelectedStudyDeckId(selectedVocabDeckId);
    setActiveTab("study");
    void loadStudyStats(selectedVocabDeckId);
    void startStudy({ deckId: selectedVocabDeckId });
  }

  function goToVocabFromStudy() {
    const vocabDeckId = isSharedDeckStudyId(selectedStudyDeckId)
      ? "all"
      : selectedStudyDeckId;
    setSelectedVocabDeckId(vocabDeckId);
    setActiveTab("vocab");
    void loadVocabItems(vocabDeckId);
    void loadCustomTerms(vocabDeckId);
  }

  async function submitStudyReview(rating: ReviewResult) {
    const currentItem = studyItems[currentStudyIndex];
    if (!currentItem) {
      return;
    }

    const responseTimeMs = answerShownAtRef.current
      ? Date.now() - answerShownAtRef.current
      : null;

    setIsReviewing(true);
    setStudyMessage("");

    try {
      let nextReviewAt: string | null;
      // item_type branches the rating submission to the right endpoint --
      // a lexeme item's rating must never touch vocab_items or /study-items
      // (see docs/architecture/shared-lexeme-progress-storage.md -- "SRS
      // card integration"). Both branches lazily update/create exactly one
      // progress row for the current word, same as before this phase.
      if (currentItem.item_type === "lexeme" && currentItem.lexeme_id !== null) {
        const progress = await requestJson<LexemeReviewResponse>(
          `/shared-decks/${currentItem.shared_deck_id}/words/${currentItem.lexeme_id}/review`,
          {
            method: "POST",
            body: JSON.stringify({ rating }),
          },
        );
        nextReviewAt = progress.next_review_at;
        setStudyItems((currentItems) =>
          currentItems.map((item) =>
            item.item_type === "lexeme" && item.lexeme_id === progress.lexeme_id
              ? {
                  ...item,
                  status: progress.status as StudyCardItem["status"],
                  review_level: progress.review_level,
                  next_review_at: progress.next_review_at,
                  correct_count: progress.correct_count,
                  wrong_count: progress.wrong_count,
                }
              : item,
          ),
        );
      } else {
        const updatedItem = await requestJson<VocabItem>(
          `/study-items/${currentItem.id}/review`,
          {
            method: "POST",
            body: JSON.stringify({ rating, response_time_ms: responseTimeMs }),
          },
        );
        nextReviewAt = updatedItem.next_review_at;
        setVocabItems((currentItems) =>
          currentItems.map((item) =>
            item.id === updatedItem.id ? updatedItem : item,
          ),
        );
      }
      setSessionCounts((counts) => ({
        ...counts,
        [rating]: counts[rating] + 1,
      }));
      setStudyMessage(buildRatingFeedbackMessage(rating, nextReviewAt));
      if (rating === "again") {
        setAgainNextReviewAt((current) => {
          if (!nextReviewAt) {
            return current;
          }
          if (!current || nextReviewAt < current) {
            return nextReviewAt;
          }
          return current;
        });
      }
      setNextUpcomingReviewAt((current) => {
        if (!nextReviewAt) {
          return current;
        }
        if (!current || nextReviewAt < current) {
          return nextReviewAt;
        }
        return current;
      });
      setCurrentStudyIndex((index) => index + 1);
      setIsAnswerVisible(false);
      answerShownAtRef.current = null;
      void loadStudyStats(selectedStudyDeckId);
      if (activeTab === "info") {
        void loadInfoStats();
      }
    } catch (error) {
      setStudyMessage(getAuthAwareErrorMessage(error, "복습 결과 저장에 실패했습니다."));
    } finally {
      setIsReviewing(false);
    }
  }

  const currentStudyItem = studyItems[currentStudyIndex];
  const isStudyComplete =
    hasStartedStudy && studyItems.length > 0 && currentStudyIndex >= studyItems.length;

  // Same "not really signed in" check AccountMenu uses internally, lifted
  // up so the landing hero's CTAs can vary by auth state too.
  const isDevUser = !currentUser || currentUser.auth_provider === "dev";

  // ---- 학습 계획 탭 입력 (Gate D) ----
  // 실제 로그인 계정만, 그리고 지금 account epoch에서 확인된 것만 넘긴다.
  const planUserId =
    currentUser && currentUser.auth_provider !== "dev" && currentUserEpoch === statsAccountEpoch
      ? currentUser.id
      : null;
  const planAccount = useMemo(
    () => (planUserId === null ? null : { userId: planUserId }),
    [planUserId],
  );
  const planPersonalDecks = useMemo(
    () =>
      planUserId !== null && decksEpoch === statsAccountEpoch && !isLoadingDecks && !deckLoadError
        ? decks.map((deck) => ({ id: deck.id, name: deck.name }))
        : null,
    [planUserId, decksEpoch, statsAccountEpoch, isLoadingDecks, deckLoadError, decks],
  );
  const planSubscribedDecks = useMemo(
    () =>
      planUserId !== null && sharedDecksEpoch === statsAccountEpoch && !isLoadingSharedDecks
        ? sharedDecks
            .filter((deck) => deck.mode === "subscribed" && deck.imported_at)
            .map((deck) => ({ id: deck.id, title: deck.title }))
        : null,
    [planUserId, sharedDecksEpoch, statsAccountEpoch, isLoadingSharedDecks, sharedDecks],
  );

  // 이전 분류 초안의 원문을 읽기 입력칸으로만 옮긴다(자동 분석·초안 삭제 없음).
  function openLegacyDraftTextInReading(text: string): boolean {
    // 지금 확인된 owner의 읽기 영역에만 원문을 연다. 분석·삭제·계정 귀속은
    // 하지 않는다(저장은 그 owner의 자동 저장 규칙을 따른다).
    if (!readingKeyRef.current || readingHydratedKey !== readingKeyRef.current) {
      window.alert("계정을 확인한 뒤 다시 시도해 주세요.");
      return false;
    }
    const hasExistingReadingWork =
      readingText.trim() !== "" || readingTokens.length > 0;
    if (
      hasExistingReadingWork &&
      !window.confirm(
        "현재 읽기 작업을 이전 분류 초안의 원문으로 바꿀까요? 기존 원문과 분석 결과가 사라지고, 초안은 그대로 남아요.",
      )
    ) {
      return false;
    }
    abortReadingAnalysis();
    bumpReadingGeneration();
    setReadingDeckConfirmRequired(false);
    setReadingText(text);
    setAnalyzedReadingText("");
    setReadingTokens([]);
    setReadingDeckVocabItems([]);
    setReadingStorageWarning("");
    setIsReadingTextCollapsed(false);
    setRecentlySavedVocabItemIds([]);
    setCurrentSelectedTokenKey(null);
    setReadingScrollFraction(null);
    setReadingTabletDocumentScrollFraction(null);
    setIsReadingSessionRestored(false);
    setReadingMessage(
      "이전 분류 초안의 원문을 불러왔어요. 분석하기를 눌러 다시 확인해 주세요. 저장하지 않은 분류 판단은 옮겨지지 않아요.",
    );
    setActiveTab("reading");
    return true;
  }

  function openAccountMenu() {
    setIsAccountMenuOpen(true);
  }

  const currentScreenLabel =
    tabs.find((tab) => tab.key === activeTab)?.label ?? activeTab;

  // Home's "오늘 복습하기" CTA: jump to the study tab and start today's
  // queue immediately, same as the study tab's own "오늘 복습 시작" quick
  // start button (quickStartStudy/startStudy are unchanged).
  function goToStudyToday() {
    setActiveTab("study");
    void loadStudyStats(selectedStudyDeckId);
    quickStartStudy("today");
  }

  // Builds one NavAction from the existing `tabs` entry for `key` -- the
  // desktop toolbar and the mobile/tablet drawer both resolve through
  // handleTabChange, so there is exactly one place tab switches actually
  // happen. Carries both label lengths since the two presentations have
  // very different room: the drawer is a vertical list with space for the
  // full label, while the desktop toolbar has to fit all 7 tabs plus the
  // brand/account/feedback on one row, so it prefers shortLabel (falls
  // back to label when a tab has no shorter form).
  function navFor(key: TabKey): NavAction {
    const tab = tabs.find((item) => item.key === key)!;
    return {
      key: tab.key,
      label: tab.label,
      shortLabel: tab.mobileLabel,
      icon: tab.icon,
      onClick: () => void handleTabChange(key),
      isActive: activeTab === key,
    };
  }

  // Feedback is an action (opens a modal), not a screen to navigate to, so
  // it isn't one of these -- it's passed to AppShell separately as
  // feedbackSlot and rendered once, in whichever of the toolbar/drawer fits
  // the current viewport.
  const navItems: NavAction[] = [
    navFor("home"),
    navFor("reading"),
    navFor("study"),
    navFor("vocab"),
    navFor("shared"),
    navFor("plan"),
    navFor("info"),
  ];

  return (
    <main className="page">
      <AppShell
        navItems={navItems}
        feedbackSlot={
          <button
            type="button"
            className="ghost-button compact-button app-topbar-feedback-button"
            onClick={openAppFeedback}
            aria-label="베타 피드백 보내기"
          >
            <ChatIcon className="button-icon" />
            <span className="app-topbar-feedback-label">피드백</span>
          </button>
        }
        accountSlot={
          <AccountMenu
            user={currentUser}
            isOpen={isAccountMenuOpen}
            onOpenChange={setIsAccountMenuOpen}
            authMode={authMode}
            email={authEmail}
            password={authPassword}
            displayName={authDisplayName}
            message={authMessage}
            isLoadingUser={isLoadingCurrentUser}
            isSubmitting={isSubmittingAuth}
            onAuthModeChange={setAuthMode}
            onEmailChange={setAuthEmail}
            onPasswordChange={setAuthPassword}
            onDisplayNameChange={setAuthDisplayName}
            onSubmit={handleAuthSubmit}
            onLogout={() => void handleLogout()}
          />
        }
      >
      <section className={`library-canvas library-canvas-${activeTab}`}>
        {activeTab === "home" ? (
          <HomeDashboard
            isDevUser={isDevUser}
            studyStats={studyStats}
            isStudyStatsLoading={isLoadingStudyStats}
            onStartReading={() => void handleTabChange("reading")}
            onTryWithSample={startSampleReadingFromHome}
            onStartTodayReview={goToStudyToday}
            onGoToStudy={() => void handleTabChange("study")}
            onOpenAccount={openAccountMenu}
            onGoToVocab={() => void handleTabChange("vocab")}
            onGoToSharedDecks={() => void handleTabChange("shared")}
            onGoToPlan={() => void handleTabChange("plan")}
            onGoToStats={() => void handleTabChange("info")}
          />
        ) : null}

        {activeTab === "plan" ? (
          <LearningPlanPanel
            account={planAccount}
            storageScope={LEARNING_PLAN_STORAGE_SCOPE}
            personalDecks={planPersonalDecks}
            subscribedDecks={planSubscribedDecks}
            request={(path) => requestJson<unknown>(path)}
            getErrorStatus={(error) => (error instanceof ApiError ? error.status : null)}
            onOpenAccount={openAccountMenu}
            onGoToHistory={() => void handleTabChange("info")}
            studyLauncher={planStudyLauncherRef.current ?? undefined}
            draftMemory={planDraftMemory}
            footer={
              <LegacyClassificationDraftNotice
                storageKey={CLASSIFICATION_DRAFT_KEY}
                onOpenInReading={openLegacyDraftTextInReading}
              />
            }
          />
        ) : null}

        {activeTab === "reading" && (readingGateState !== "ready" || readingHydratedKey !== readingOwnerKey) ? (
          <ReadingAccountGate
            failed={readingGateState === "failed"}
            onRetry={() => void loadCurrentUser()}
          />
        ) : null}

        {activeTab === "reading" && readingGateState === "ready" && readingHydratedKey === readingOwnerKey ? (
          <ReadingStorageNotice
            ownerLabel={readingOwnerLabel()}
            status={readingStorageStatus}
            unverifiedAction={readingLastAttemptKind}
            offer={readingRecoveryOffer}
            hasUnsavedRecovery={readingRecoveryAvailable}
            deckConfirm={
              readingDeckConfirmRequired
                ? {
                    deckName:
                      decks.find((deck) => String(deck.id) === readingSelectedDeckId)?.name ?? "",
                  }
                : null
            }
            busy={isReadingNoticeBusy}
            deckConfirmBusy={isReadingDeckConfirmBusy}
            message={readingNoticeMessage}
            saveWarning={readingStorageWarning}
            onCopy={(source, mode) => void copyIntoCurrentReading(source, mode)}
            onDownloadLegacy={downloadLegacyReadingRaw}
            onDismissOffer={() => setReadingRecoveryOffer(null)}
            onDownloadCurrent={downloadCurrentReadingText}
            onLoadStored={loadStoredReadingIntoWindow}
            onRecheck={recheckReadingStorage}
            onDownloadStoredRaw={downloadStoredReadingRaw}
            onResetCorrupt={() => void resetCorruptReadingStorage()}
            onRestoreRecovery={restoreReadingRecovery}
            onDownloadRecovery={downloadReadingRecovery}
            onDiscardRecovery={discardReadingRecovery}
            onConfirmDeck={() => void confirmImportedReadingDeck()}
          />
        ) : null}

        {readingSwitchPrompt ? (
          <ReadingSwitchDialog
            reason={readingSwitchPrompt.reason}
            onStay={() => resolveReadingSwitch(false)}
            onDownload={downloadCurrentReadingText}
            onContinue={() => resolveReadingSwitch(true)}
          />
        ) : null}

        {activeTab === "reading" && readingGateState === "ready" && readingHydratedKey === readingOwnerKey ? (
          <ReadingTab
            key={`reading-${readingGeneration}`}
            text={readingText}
            analyzedText={analyzedReadingText}
            tokens={readingTokens}
            vocabItems={readingDeckVocabItems}
            decks={decks}
            isLoadingDecks={isLoadingDecks}
            deckLoadError={deckLoadError}
            onRetryLoadDecks={() => void loadDecks()}
            selectedDeckId={readingSelectedDeckId}
            isAnalyzing={isReadingAnalyzing}
            analyzeProgress={readingAnalyzeProgress}
            onCancelAnalyze={cancelReadingAnalyze}
            message={readingMessage}
            storageWarning=""
            isTextCollapsed={isReadingTextCollapsed}
            isSavingBatch={isSavingReadingBatch}
            recentlySavedCount={recentlySavedVocabItemIds.length}
            isSessionRestored={isReadingSessionRestored}
            selectedTokenKey={currentSelectedTokenKey}
            scrollFraction={readingScrollFraction}
            onScrollProgressChange={setReadingScrollFraction}
            tabletDocumentScrollFraction={readingTabletDocumentScrollFraction}
            onTabletDocumentScrollChange={setReadingTabletDocumentScrollFraction}
            onTextChange={setReadingText}
            onLoadSampleText={loadSampleReadingText}
            onSelectedDeckChange={handleReadingDeckChange}
            onAnalyze={handleReadingAnalyze}
            onStatusChange={(index, status) =>
              void handleReadingStatusChange(index, status)
            }
            onToggleTextCollapsed={toggleReadingTextCollapsed}
            onSaveSelected={saveSelectedReadingTokens}
            onStartStudyFromSaved={startStudyFromRecentlySaved}
            onGoToVocab={goToVocabFromReading}
            onSelectedTokenKeyChange={handleReadingSelectedTokenKeyChange}
            onDismissRestoredNotice={dismissRestoredReadingNotice}
            onResetSession={resetReadingSession}
            meaningEditItemId={meaningEditItemId}
            meaningEditDraft={meaningEditDraft}
            isSavingMeaningEdit={isSavingMeaningEdit}
            meaningEditMessage={meaningEditMessage}
            onStartMeaningEdit={startMeaningEdit}
            onMeaningEditDraftChange={setMeaningEditDraft}
            onSaveMeaningEdit={() => void saveMeaningEdit()}
            onCancelMeaningEdit={cancelMeaningEdit}
            onReportMeaning={(token) =>
              openMeaningFeedback({
                vocabularyId: token.savedVocabItemId ?? null,
                surface: token.surface,
                baseForm: token.base_form,
                reading: token.reading,
                currentMeaningKo: token.savedMeaningKo || token.meaning_ko,
                source: "reading",
              })
            }
          />
        ) : null}

        {activeTab === "vocab" ? (
          <VocabSection
            items={vocabItems}
            stats={studyStats}
            isLoading={isLoadingVocab}
            isExportingCsv={isExportingCsv}
            isExportingDeckPackage={isExportingDeckPackage}
            isImportingDeckPackage={isImportingDeckPackage}
            isPublishingDeck={isPublishingDeck}
            message={vocabMessage}
            decks={decks}
            selectedDeckId={selectedVocabDeckId}
            defaultDeckId={defaultDeck ? String(defaultDeck.id) : ""}
            searchText={vocabSearch}
            statusFilter={vocabStatusFilter}
            dueOnly={vocabDueOnly}
            sortValue={vocabSort}
            newDeckName={newDeckName}
            newDeckDescription={newDeckDescription}
            isCreatingDeck={isCreatingDeck}
            isAddingVocab={isAddingVocab}
            isUpdatingVocab={isUpdatingVocab}
            isNewVocabFormOpen={isNewVocabFormOpen}
            deckMessage={deckMessage}
            newVocabForm={newVocabForm}
            editingItemId={editingItemId}
            editVocabForm={editVocabForm}
            customTerms={customTerms}
            newCustomTermForm={newCustomTermForm}
            editCustomTermForm={editCustomTermForm}
            isCustomTermFormOpen={isCustomTermFormOpen}
            editingCustomTermId={editingCustomTermId}
            isSavingCustomTerm={isSavingCustomTerm}
            deckPackageFileName={deckPackageFile?.name ?? ""}
            publishTitle={publishTitle}
            publishDescription={publishDescription}
            onSelectedDeckChange={(deckId) => void changeVocabDeck(deckId)}
            onSearchTextChange={setVocabSearch}
            onStatusFilterChange={setVocabStatusFilter}
            onDueOnlyChange={setVocabDueOnly}
            onSortChange={setVocabSort}
            onNewDeckNameChange={setNewDeckName}
            onNewDeckDescriptionChange={setNewDeckDescription}
            onCreateDeck={() => void createDeck()}
            onDeleteDeck={(deckId) => void deleteDeck(deckId)}
            onNewVocabFormOpenChange={setIsNewVocabFormOpen}
            onNewVocabFormChange={updateNewVocabForm}
            onAddVocabItem={() => void addVocabItem()}
            onCustomTermFormOpenChange={setIsCustomTermFormOpen}
            onNewCustomTermFormChange={updateNewCustomTermForm}
            onAddCustomTerm={() => void addCustomTerm()}
            onEditCustomTermFormChange={updateEditCustomTermForm}
            onStartCustomTermEdit={startEditingCustomTerm}
            onSaveCustomTermEdit={() => void saveEditedCustomTerm()}
            onCancelCustomTermEdit={cancelEditingCustomTerm}
            onDeleteCustomTerm={(termId) => void deleteCustomTerm(termId)}
            onEditVocabFormChange={updateEditVocabForm}
            onStartEdit={startEditingVocabItem}
            onSaveEdit={() => void saveEditedVocabItem()}
            onCancelEdit={cancelEditingVocabItem}
            meaningEditItemId={meaningEditItemId}
            meaningEditDraft={meaningEditDraft}
            isSavingMeaningEdit={isSavingMeaningEdit}
            meaningEditMessage={meaningEditMessage}
            onStartMeaningEdit={startMeaningEdit}
            onMeaningEditDraftChange={setMeaningEditDraft}
            onSaveMeaningEdit={() => void saveMeaningEdit()}
            onCancelMeaningEdit={cancelMeaningEdit}
            onReportMeaning={(item) =>
              openMeaningFeedback({
                vocabularyId: item.id,
                surface: item.surface,
                baseForm: item.base_form,
                reading: item.reading,
                currentMeaningKo: item.meaning_ko,
                source: "vocab",
              })
            }
            onRefresh={() => void loadVocabItems(selectedVocabDeckId)}
            onDownloadCsv={() => void downloadCsv()}
            onExportDeckPackage={() => void exportDeckPackage()}
            onDeckPackageFileChange={setDeckPackageFile}
            onImportDeckPackage={() => void importDeckPackage()}
            onPublishTitleChange={setPublishTitle}
            onPublishDescriptionChange={setPublishDescription}
            onPublishDeck={() => void publishCurrentDeck()}
            onStudySelectedDeck={startStudyFromVocabDeck}
            onStatusChange={(itemId, status) =>
              void updateVocabStatus(itemId, status)
            }
            onDelete={(itemId) => void deleteVocabItem(itemId)}
            onGoToReading={() => setActiveTab("reading")}
            onGoToStudyToday={goToStudyToday}
            onGoToShared={() => void handleTabChange("shared")}
          />
        ) : null}

        {activeTab === "shared" ? (
          <SharedDeckSection
            decks={sharedDecks}
            selectedDeck={selectedSharedDeck}
            selectedDeckId={selectedSharedDeckId}
            isLoading={isLoadingSharedDecks}
            isLoadingDetail={isLoadingSharedDeckDetail}
            importingDeckId={importingSharedDeckId}
            importedDeckId={importedSharedDeckId}
            unpublishingDeckId={unpublishingSharedDeckId}
            republishingDeckId={republishingSharedDeckId}
            canManageSharedDecks={!isDevUser}
            message={sharedDeckMessage}
            updatingWordLexemeId={updatingWordLexemeId}
            onRefresh={() => void loadSharedDecks()}
            onSelectDeck={(deckId) => void loadSharedDeckDetail(deckId)}
            onCloseDetail={closeSharedDeckDetail}
            onImportDeck={(deckId) => void importSharedDeckToMyDeck(deckId)}
            onUnpublishDeck={(deckId) => void unpublishSharedDeck(deckId)}
            onRepublishSharedDeck={(deckId) => void republishSharedDeck(deckId)}
            onUpdateWordStatus={(sharedDeckId, lexemeId, status) =>
              void updateSharedDeckWordStatus(sharedDeckId, lexemeId, status)
            }
            onGoToVocab={goToVocabTab}
            onGoToStudyToday={goToStudyToday}
          />
        ) : null}

        {activeTab === "study" ? (
          <StudySection
            items={studyItems}
            currentItem={currentStudyItem}
            currentIndex={currentStudyIndex}
            isComplete={isStudyComplete}
            isAnswerVisible={isAnswerVisible}
            isLoading={isLoadingStudy}
            isReviewing={isReviewing}
            message={studyMessage}
            stats={studyStats}
            isStatsLoading={isLoadingStudyStats}
            statsMessage={studyStatsMessage}
            sessionCounts={sessionCounts}
            nextUpcomingReviewAt={nextUpcomingReviewAt}
            againNextReviewAt={againNextReviewAt}
            decks={decks}
            sharedDeckOptions={sharedDecks
              .filter((deck) => deck.mode === "subscribed" && deck.imported_at)
              .map((deck) => ({
                id: `${SHARED_DECK_STUDY_ID_PREFIX}${deck.id}`,
                title: deck.title,
              }))}
            selectedDeckId={selectedStudyDeckId}
            selectedDeckName={getDeckDisplayName(selectedStudyDeckId)}
            studyMode={studyMode}
            hasStarted={hasStartedStudy}
            meaningEditItemId={meaningEditItemId}
            meaningEditDraft={meaningEditDraft}
            isSavingMeaningEdit={isSavingMeaningEdit}
            meaningEditMessage={meaningEditMessage}
            onStartMeaningEdit={startMeaningEdit}
            onMeaningEditDraftChange={setMeaningEditDraft}
            onSaveMeaningEdit={() => void saveMeaningEdit()}
            onCancelMeaningEdit={cancelMeaningEdit}
            onReportMeaning={(item) =>
              openMeaningFeedback({
                vocabularyId: item.id,
                surface: item.surface,
                baseForm: item.base_form,
                reading: item.reading,
                currentMeaningKo: item.meaning_ko,
                source: "review",
              })
            }
            onSelectedDeckChange={changeStudyDeck}
            onStudyModeChange={changeStudyMode}
            onQuickStart={quickStartStudy}
            onStart={() => void startStudy()}
            onRestart={() => void startStudy()}
            onGoToVocab={goToVocabFromStudy}
            onGoToReading={() => setActiveTab("reading")}
            onShowAnswer={() => {
              answerShownAtRef.current = Date.now();
              setIsAnswerVisible(true);
            }}
            onReview={(result) => void submitStudyReview(result)}
            isGuest={currentUser?.auth_provider === "dev"}
            onOpenAccount={openAccountMenu}
          />
        ) : null}

        {activeTab === "info" ? (
          <StudyLogPage
            key={`${statsAccountEpoch}:${currentUser?.id ?? "none"}`}
            stats={infoStats}
            isStatsLoading={isLoadingInfoStats}
            statsMessage={infoStatsMessage}
            recentWords={infoRecentWords}
            hardWords={infoHardWords}
            isWordsLoading={isLoadingInfoWords}
            onGoToVocab={() => void handleTabChange("vocab")}
            onGoToReading={() => void handleTabChange("reading")}
            loadHistoryMonth={(month) =>
              requestJson<StudyHistoryMonth>(
                `/stats/history?month=${encodeURIComponent(month)}`,
              )
            }
            loadHistoryDay={(date) =>
              requestJson<StudyHistoryDay>(
                `/stats/history/day?date=${encodeURIComponent(date)}&limit=5`,
              )
            }
          />
        ) : null}
      </section>
      </AppShell>

      {meaningFeedbackTarget ? (
        <MeaningFeedbackModal
          target={meaningFeedbackTarget}
          suggestedMeaning={feedbackSuggestedMeaning}
          reason={feedbackReason}
          isSubmitting={isSubmittingFeedback}
          message={feedbackMessage}
          onSuggestedMeaningChange={setFeedbackSuggestedMeaning}
          onReasonChange={setFeedbackReason}
          onSubmit={() => void submitMeaningFeedback()}
          onClose={closeMeaningFeedback}
        />
      ) : null}

      {isAppFeedbackOpen ? (
        <GlobalFeedbackModal
          screenLabel={currentScreenLabel}
          category={appFeedbackCategory}
          message={appFeedbackDraft}
          isSubmitting={isSubmittingAppFeedback}
          resultMessage={appFeedbackResultMessage}
          onCategoryChange={setAppFeedbackCategory}
          onMessageChange={setAppFeedbackDraft}
          onSubmit={() => void submitAppFeedback()}
          onClose={closeAppFeedback}
        />
      ) : null}
    </main>
  );
}

async function requestJson<T>(
  path: string,
  init: RequestInit = {},
  options: { includeAuth?: boolean } = {},
): Promise<T> {
  const response = await apiFetch(path, init, options);

  if (!response.ok) {
    let rawDetail = "";
    try {
      const data = (await response.json()) as { detail?: unknown };
      rawDetail = normalizeHttpDetail(data.detail);
    } catch {
      rawDetail = "";
    }
    const suffix = rawDetail ? ` ${rawDetail}` : "";
    throw new ApiError(
      response.status,
      getHttpErrorMessage(response.status, suffix),
      rawDetail,
    );
  }

  return (await response.json()) as T;
}

async function apiFetch(
  path: string,
  init: RequestInit = {},
  options: { includeAuth?: boolean } = {},
) {
  const includeAuth = options.includeAuth ?? true;
  const token = includeAuth ? getAccessToken() : "";
  const headers = new Headers(init.headers);
  if (!headers.has("Content-Type") && init.body) {
    headers.set("Content-Type", "application/json");
  }
  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers,
  });
  // Only the token this request was sent with may be dropped: a slow 401
  // from a previous account must not sign out whoever is signed in now.
  if (includeAuth && token && response.status === 401 && getAccessToken() === token) {
    clearAccessToken();
    window.dispatchEvent(new Event(AUTH_EXPIRED_EVENT));
  }
  return response;
}

// Fired by apiFetch when the current token is rejected mid-session (the /me
// check on load handles its own 401). Home listens and runs the same
// account-boundary reset as sign-out.
const AUTH_EXPIRED_EVENT = "jv-auth-expired";

function getAccessToken() {
  if (typeof window === "undefined") {
    return "";
  }
  return window.localStorage.getItem(ACCESS_TOKEN_KEY) ?? "";
}

function setAccessToken(token: string) {
  window.localStorage.setItem(ACCESS_TOKEN_KEY, token);
}

function clearAccessToken() {
  window.localStorage.removeItem(ACCESS_TOKEN_KEY);
}

// Technical detail (HTTP status, raw backend `detail` text) is useful for
// debugging but was previously shown to the user verbatim via
// `error.message` -- e.g. "지금은 처리할 수 없어요. (400) value is not a
// valid email address". Every call site already passes a friendly,
// action-specific `fallback` string for exactly this case, so this now
// always shows that instead and keeps the technical detail in the console
// only (개발용 상세 오류는 console에만 유지, 사용자에게는 노출하지 않음).
function getErrorMessage(error: unknown, fallback: string) {
  if (error instanceof Error) {
    console.error(error);
  }
  return fallback;
}

// Same as getErrorMessage, but for actions that only work for a signed-in
// user (saving words, viewing vocab/study data, shared-deck import/publish).
// A 401 here always means "the stored token is stale/invalid", never
// "logged out" -- every endpoint falls back to the dev user when no token is
// sent at all -- so this always points the learner at logging back in
// rather than repeating the generic HTTP status text.
function getAuthAwareErrorMessage(error: unknown, fallback: string) {
  if (isHttpError(error, 401)) {
    return "로그인 후 사용할 수 있습니다. 저장한 단어와 복습 기록을 이어서 보려면 로그인해주세요.";
  }
  return getErrorMessage(error, fallback);
}

class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
    readonly detail: string = "",
  ) {
    super(message);
    this.name = "ApiError";
  }
}

function isHttpError(error: unknown, status: number) {
  return error instanceof ApiError && error.status === status;
}

function normalizeHttpDetail(detail: unknown) {
  if (typeof detail === "string") {
    return detail;
  }
  if (Array.isArray(detail)) {
    return detail
      .map((item) => {
        if (typeof item === "string") {
          return item;
        }
        if (item && typeof item === "object" && "msg" in item) {
          const message = (item as { msg?: unknown }).msg;
          return typeof message === "string" ? message : "";
        }
        return "";
      })
      .filter(Boolean)
      .join("; ");
  }
  return "";
}

function getHttpErrorMessage(status: number, detail: string) {
  const suffix = detail.trim() ? ` ${detail.trim()}` : "";
  if (status === 400) {
    return `요청 값을 확인해 주세요. (${status})${suffix}`;
  }
  if (status === 401) {
    return `로그인이 필요하거나 로그인이 만료되었습니다. 로그인 후 다시 시도해주세요. (${status})${suffix}`;
  }
  if (status === 404) {
    return `대상을 찾을 수 없습니다. (${status})${suffix}`;
  }
  if (status >= 500) {
    return `지금은 서버에 연결하기 어려워요. 잠시 후 다시 시도해 주세요. (${status})${suffix}`;
  }
  return `지금은 처리할 수 없어요. 잠시 후 다시 시도해주세요. (${status})${suffix}`;
}
