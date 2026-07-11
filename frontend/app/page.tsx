"use client";

import { FormEvent, useEffect, useRef, useState } from "react";
import { AnalyzeSection } from "../components/AnalyzeSection";
import { GlobalFeedbackModal } from "../components/GlobalFeedbackModal";
import {
  getTokenGroupKey,
  getTokenStatus,
  resolveReadingSaveTargets,
} from "../components/coverageUtils";
import type { ReadingSaveMode } from "../components/coverageUtils";
import { InfoSection } from "../components/InfoSection";
import { MeaningFeedbackModal } from "../components/MeaningFeedbackModal";
import {
  analyzeLongTextInChunks,
  type ChunkAnalyzeProgress,
} from "../components/readingChunkAnalyze";
import { ReadingTab } from "../components/ReadingTab";
import { SharedDeckSection } from "../components/SharedDeckSection";
import { withObjectParticle } from "../components/shared";
import { splitTextIntoChunks } from "../components/textChunking";
import { StudySection } from "../components/StudySection";
import { VocabSection } from "../components/VocabSection";
import type {
  ReviewResult,
  AppFeedbackCategory,
  Deck,
  MeaningFeedbackTarget,
  QualityTag,
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
  StudyStats,
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
};

type SharedDeckDeleteResponse = {
  ok: boolean;
  shared_deck_id: number;
  title: string;
  message: string;
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

type TabKey = "analyze" | "reading" | "vocab" | "study" | "shared" | "info";
type VocabStatusFilter = "all" | TokenStatus;

type ClassificationDraft = {
  text: string;
  deck_id: string;
  include_known: boolean;
  tokens: TokenWithStatus[];
  current_index: number;
  is_complete: boolean;
  saved_at: string;
};

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL || "http://127.0.0.1:8000";
const CLASSIFICATION_DRAFT_KEY = "jp-vocab-reader:classification-draft";
const ACCESS_TOKEN_KEY = "jp-vocab-reader:access-token";

const tabs: Array<{ key: TabKey; label: string }> = [
  { key: "analyze", label: "분석" },
  { key: "reading", label: "읽기" },
  { key: "vocab", label: "단어장" },
  { key: "study", label: "학습" },
  { key: "shared", label: "공유덱" },
  { key: "info", label: "정보" },
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

function isTokenStatus(value: unknown): value is TokenStatus {
  return (
    value === "known" ||
    value === "uncertain" ||
    value === "unknown" ||
    value === "unclassified"
  );
}

function isQualityTag(value: unknown): value is QualityTag {
  return (
    value === "normal" ||
    value === "custom_term" ||
    value === "compound_verb" ||
    value === "noun_phrase_candidate" ||
    value === "known_phrase"
  );
}

function parseClassificationDraft(value: string | null): ClassificationDraft | null {
  if (!value) {
    return null;
  }

  try {
    const parsed = JSON.parse(value) as Partial<ClassificationDraft>;
    if (
      typeof parsed.text !== "string" ||
      typeof parsed.deck_id !== "string" ||
      typeof parsed.include_known !== "boolean" ||
      !Array.isArray(parsed.tokens) ||
      typeof parsed.current_index !== "number" ||
      typeof parsed.is_complete !== "boolean" ||
      typeof parsed.saved_at !== "string"
    ) {
      return null;
    }

    const tokens = parsed.tokens.map((token) => {
      if (
        typeof token.surface !== "string" ||
        typeof token.base_form !== "string" ||
        typeof token.reading !== "string" ||
        typeof token.part_of_speech !== "string" ||
        typeof token.normalized_form !== "string" ||
        typeof token.meaning_ko !== "string" ||
        typeof token.example_sentence !== "string" ||
        !isTokenStatus(token.status)
      ) {
        throw new Error("invalid token");
      }
      return {
        ...token,
        dictionary_gloss:
          typeof token.dictionary_gloss === "string"
            ? token.dictionary_gloss
            : "",
        quality_tag: isQualityTag(token.quality_tag)
          ? token.quality_tag
          : token.is_custom_term
            ? "custom_term"
            : "normal",
        is_custom_term:
          typeof token.is_custom_term === "boolean"
            ? token.is_custom_term
            : false,
        isClassified:
          typeof token.isClassified === "boolean"
            ? token.isClassified
            : token.status !== "unclassified",
      };
    });

    const currentIndex = parsed.is_complete
      ? tokens.length
      : Math.max(0, Math.min(parsed.current_index, tokens.length));

    return {
      text: parsed.text,
      deck_id: parsed.deck_id,
      include_known: parsed.include_known,
      tokens,
      current_index: currentIndex,
      is_complete: parsed.is_complete,
      saved_at: parsed.saved_at,
    };
  } catch {
    return null;
  }
}

// Reading-tab work-in-progress persistence -- browser-local only (never
// sent to the server beyond the existing /analyze call). Lets a user
// refresh or switch tabs and pick the reading session back up: original
// text, analyzed tokens/status, the selected word, and the last save
// message. Deliberately excludes readingDeckVocabItems -- that's re-fetched
// fresh on restore so "already saved"/example-sentence state reflects the
// live server rather than a possibly-stale local copy.
const READING_SESSION_KEY = "jp-vocab-reader:reading-session-v1";
// Long original texts (chunk-analyzed novels/web-novel excerpts) can now
// legitimately run well past the old 20,000-char ceiling -- raised so a
// full chunked read still gets to persist locally. Still bounded (and still
// wrapped in try/catch below) so a truly enormous paste can't hang the tab
// on a slow localStorage write or silently blow the origin's quota.
const MAX_READING_SESSION_TEXT_LENGTH = 200000;
const MAX_MEANING_KO_LENGTH = 200;

type ReadingSession = {
  version: 1;
  originalText: string;
  analyzedText: string;
  deckId: string;
  tokens: TokenWithStatus[];
  selectedTokenKey: string | null;
  message: string;
  isTextCollapsed: boolean;
  recentlySavedVocabItemIds: number[];
  updatedAt: string;
};

function parseReadingSession(value: string | null): ReadingSession | null {
  if (!value) {
    return null;
  }

  try {
    const parsed = JSON.parse(value) as Partial<ReadingSession>;
    if (
      parsed.version !== 1 ||
      typeof parsed.originalText !== "string" ||
      typeof parsed.analyzedText !== "string" ||
      typeof parsed.deckId !== "string" ||
      !Array.isArray(parsed.tokens) ||
      typeof parsed.message !== "string" ||
      typeof parsed.isTextCollapsed !== "boolean" ||
      !Array.isArray(parsed.recentlySavedVocabItemIds) ||
      typeof parsed.updatedAt !== "string"
    ) {
      return null;
    }

    const tokens = parsed.tokens.map((token) => {
      if (
        typeof token.surface !== "string" ||
        typeof token.base_form !== "string" ||
        typeof token.reading !== "string" ||
        typeof token.part_of_speech !== "string" ||
        typeof token.normalized_form !== "string" ||
        typeof token.meaning_ko !== "string" ||
        typeof token.example_sentence !== "string" ||
        !isTokenStatus(token.status)
      ) {
        throw new Error("invalid token");
      }
      return {
        ...token,
        dictionary_gloss:
          typeof token.dictionary_gloss === "string"
            ? token.dictionary_gloss
            : "",
        quality_tag: isQualityTag(token.quality_tag)
          ? token.quality_tag
          : token.is_custom_term
            ? "custom_term"
            : "normal",
        is_custom_term:
          typeof token.is_custom_term === "boolean"
            ? token.is_custom_term
            : false,
        occurrence_count:
          typeof token.occurrence_count === "number"
            ? token.occurrence_count
            : 1,
        isClassified:
          typeof token.isClassified === "boolean"
            ? token.isClassified
            : token.status !== "unclassified",
        savedExampleSentence:
          typeof token.savedExampleSentence === "string" ||
          token.savedExampleSentence === null
            ? token.savedExampleSentence
            : null,
      };
    });

    const recentlySavedVocabItemIds = parsed.recentlySavedVocabItemIds.filter(
      (id): id is number => typeof id === "number",
    );

    return {
      version: 1,
      originalText: parsed.originalText,
      analyzedText: parsed.analyzedText,
      deckId: parsed.deckId,
      tokens,
      selectedTokenKey:
        typeof parsed.selectedTokenKey === "string"
          ? parsed.selectedTokenKey
          : null,
      message: parsed.message,
      isTextCollapsed: parsed.isTextCollapsed,
      recentlySavedVocabItemIds,
      updatedAt: parsed.updatedAt,
    };
  } catch {
    return null;
  }
}

// Returns whether the session was actually persisted (or intentionally
// cleared because there was nothing to save) -- false means "skipped due to
// size or a localStorage failure", which the caller surfaces as a soft
// inline notice rather than silently losing the user's place.
function persistReadingSession(
  session: Omit<ReadingSession, "version" | "updatedAt">,
): boolean {
  if (typeof window === "undefined") {
    return true;
  }
  try {
    if (
      session.originalText.length > MAX_READING_SESSION_TEXT_LENGTH ||
      session.analyzedText.length > MAX_READING_SESSION_TEXT_LENGTH
    ) {
      // Too long to keep re-persisting on every keystroke -- drop it rather
      // than risk a slow/failing localStorage write, or restoring a huge
      // blob later. The user can still work with it in-memory this session.
      window.localStorage.removeItem(READING_SESSION_KEY);
      return false;
    }
    if (!session.originalText && session.tokens.length === 0) {
      window.localStorage.removeItem(READING_SESSION_KEY);
      return true;
    }
    const payload: ReadingSession = {
      version: 1,
      ...session,
      updatedAt: new Date().toISOString(),
    };
    window.localStorage.setItem(READING_SESSION_KEY, JSON.stringify(payload));
    return true;
  } catch {
    // localStorage can throw (quota exceeded, disabled, private mode) --
    // never let persistence failures break the reading tab itself.
    return false;
  }
}

function clearReadingSession() {
  if (typeof window === "undefined") {
    return;
  }
  try {
    window.localStorage.removeItem(READING_SESSION_KEY);
  } catch {
    // ignore
  }
}

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
  const [activeTab, setActiveTab] = useState<TabKey>("analyze");
  const [hasLoadedVocab, setHasLoadedVocab] = useState(false);
  const [decks, setDecks] = useState<Deck[]>([]);
  const [selectedSaveDeckId, setSelectedSaveDeckId] = useState("");
  const [selectedVocabDeckId, setSelectedVocabDeckId] = useState("all");
  const [selectedStudyDeckId, setSelectedStudyDeckId] = useState("all");
  const [studyMode, setStudyMode] = useState<StudyMode>("today");
  const [includeKnown, setIncludeKnown] = useState(false);
  const [currentAnalyzeCardIndex, setCurrentAnalyzeCardIndex] = useState(0);
  const [showAllAnalyzeResults, setShowAllAnalyzeResults] = useState(false);
  const [pendingClassificationDraft, setPendingClassificationDraft] =
    useState<ClassificationDraft | null>(null);
  const [classificationDraftSavedAt, setClassificationDraftSavedAt] =
    useState("");
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
  const [text, setText] = useState("");
  const [tokens, setTokens] = useState<TokenWithStatus[]>([]);
  const [ignoredTokenCount, setIgnoredTokenCount] = useState(0);
  const [deckVocabItems, setDeckVocabItems] = useState<VocabItem[]>([]);
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
  const [isReadingTextCollapsed, setIsReadingTextCollapsed] = useState(false);
  const [isSavingReadingBatch, setIsSavingReadingBatch] = useState(false);
  const [recentlySavedVocabItemIds, setRecentlySavedVocabItemIds] = useState<
    number[]
  >([]);
  const [currentSelectedTokenKey, setCurrentSelectedTokenKey] = useState<
    string | null
  >(null);
  const [isReadingSessionRestored, setIsReadingSessionRestored] =
    useState(false);
  const [vocabItems, setVocabItems] = useState<VocabItem[]>([]);
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
  const [isSavingMeaningEdit, setIsSavingMeaningEdit] = useState(false);
  const [meaningEditMessage, setMeaningEditMessage] = useState("");
  // "뜻 오류 신고" -- one shared modal, openable from any of the same three
  // places, tracked centrally so only one report can be in progress at once.
  const [meaningFeedbackTarget, setMeaningFeedbackTarget] =
    useState<MeaningFeedbackTarget | null>(null);
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
  const [studyItems, setStudyItems] = useState<VocabItem[]>([]);
  const [studyStats, setStudyStats] = useState<StudyStats | null>(null);
  const [infoStats, setInfoStats] = useState<StudyStats | null>(null);
  const [currentStudyIndex, setCurrentStudyIndex] = useState(0);
  const [isAnswerVisible, setIsAnswerVisible] = useState(false);
  const [sessionCounts, setSessionCounts] = useState<SessionReviewCounts>(
    createEmptySessionCounts(),
  );
  const [nextUpcomingReviewAt, setNextUpcomingReviewAt] = useState<string | null>(
    null,
  );
  const answerShownAtRef = useRef<number | null>(null);
  const [hasStartedStudy, setHasStartedStudy] = useState(false);
  const [isLoadingStudyStats, setIsLoadingStudyStats] = useState(false);
  const [isLoadingInfoStats, setIsLoadingInfoStats] = useState(false);
  const [currentUser, setCurrentUser] = useState<CurrentUser | null>(null);
  const [isLoadingCurrentUser, setIsLoadingCurrentUser] = useState(false);
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
  const [publishTitle, setPublishTitle] = useState("");
  const [publishDescription, setPublishDescription] = useState("");
  const [isPublishingDeck, setIsPublishingDeck] = useState(false);

  function resetStudySession() {
    setStudyItems([]);
    setCurrentStudyIndex(0);
    setHasStartedStudy(false);
    setIsAnswerVisible(false);
    setStudyMessage("");
    setSessionCounts(createEmptySessionCounts());
    setNextUpcomingReviewAt(null);
    answerShownAtRef.current = null;
  }

  useEffect(() => {
    void initializeUserSession();
    const draft = parseClassificationDraft(
      window.localStorage.getItem(CLASSIFICATION_DRAFT_KEY),
    );
    if (draft) {
      setPendingClassificationDraft(draft);
      setClassificationDraftSavedAt(draft.saved_at);
    } else {
      window.localStorage.removeItem(CLASSIFICATION_DRAFT_KEY);
    }

    const readingSession = parseReadingSession(
      window.localStorage.getItem(READING_SESSION_KEY),
    );
    if (readingSession) {
      setReadingText(readingSession.originalText);
      setAnalyzedReadingText(readingSession.analyzedText);
      setReadingSelectedDeckId(readingSession.deckId);
      setReadingTokens(readingSession.tokens);
      setReadingMessage(readingSession.message);
      setIsReadingTextCollapsed(readingSession.isTextCollapsed);
      setRecentlySavedVocabItemIds(readingSession.recentlySavedVocabItemIds);
      setCurrentSelectedTokenKey(readingSession.selectedTokenKey);
      setIsReadingSessionRestored(true);
      if (readingSession.deckId && readingSession.tokens.length > 0) {
        void refreshReadingDeckVocabItems(
          readingSession.deckId,
          readingSession.tokens,
        );
      }
    } else {
      clearReadingSession();
    }
  }, []);

  // Debounced auto-save: covers every meaningful reading-tab checkpoint
  // (analyze complete, per-word status change, batch save, word selection,
  // and textarea edits) in one place, rather than threading explicit
  // persist calls through each handler. A short debounce keeps large-text
  // typing from writing to localStorage on every keystroke.
  useEffect(() => {
    const timeoutId = window.setTimeout(() => {
      const persisted = persistReadingSession({
        originalText: readingText,
        analyzedText: analyzedReadingText,
        deckId: readingSelectedDeckId,
        tokens: readingTokens,
        selectedTokenKey: currentSelectedTokenKey,
        message: readingMessage,
        isTextCollapsed: isReadingTextCollapsed,
        recentlySavedVocabItemIds,
      });
      setReadingStorageWarning(
        persisted
          ? ""
          : "브라우저 저장 공간이 부족해 이어읽기 저장은 생략되었습니다.",
      );
    }, 600);
    return () => window.clearTimeout(timeoutId);
  }, [
    readingText,
    analyzedReadingText,
    readingSelectedDeckId,
    readingTokens,
    currentSelectedTokenKey,
    readingMessage,
    isReadingTextCollapsed,
    recentlySavedVocabItemIds,
  ]);

  async function initializeUserSession() {
    await loadCurrentUser();
    await refreshUserScopedData();
  }

  useEffect(() => {
    if (tokens.length === 0) {
      return;
    }

    const savedAt = new Date().toISOString();
    const draft: ClassificationDraft = {
      text,
      deck_id: selectedSaveDeckId,
      include_known: includeKnown,
      tokens,
      current_index: currentAnalyzeCardIndex,
      is_complete: currentAnalyzeCardIndex >= tokens.length,
      saved_at: savedAt,
    };
    window.localStorage.setItem(
      CLASSIFICATION_DRAFT_KEY,
      JSON.stringify(draft),
    );
    setClassificationDraftSavedAt(savedAt);
    setPendingClassificationDraft(null);
  }, [text, selectedSaveDeckId, includeKnown, tokens, currentAnalyzeCardIndex]);

  const defaultDeck =
    decks.find((deck) => deck.name === "기본 단어장") ?? decks[0];
  const defaultVocabFormDeckId =
    selectedVocabDeckId !== "all"
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

  useEffect(() => {
    if (activeTab === "vocab" && hasLoadedVocab) {
      void loadVocabItems();
      void loadCustomTerms();
    }
  }, [
    activeTab,
    hasLoadedVocab,
    selectedVocabDeckId,
    vocabSearch,
    vocabStatusFilter,
    vocabDueOnly,
    vocabSort,
  ]);

  async function handleTabChange(tab: TabKey) {
    setActiveTab(tab);
    if (tab === "vocab" && !hasLoadedVocab) {
      setHasLoadedVocab(true);
    }
    if (tab === "study") {
      void loadStudyStats(selectedStudyDeckId);
    }
    if (tab === "shared") {
      void loadSharedDecks();
    }
    if (tab === "info") {
      void loadInfoStats();
    }
  }

  async function refreshUserScopedData() {
    setSelectedVocabDeckId("all");
    setSelectedStudyDeckId("all");
    await loadDecks();
    await loadVocabItems("all");
    await loadCustomTerms("all");
    await loadStudyStats("all");
    await loadInfoStats();
    await loadSharedDecks();
    resetStudySession();
  }

  async function loadCurrentUser() {
    setIsLoadingCurrentUser(true);
    try {
      const user = await requestJson<CurrentUser>("/me");
      setCurrentUser(user);
    } catch (error) {
      if (isHttpError(error, 401)) {
        clearAccessToken();
        const devUser = await requestJson<CurrentUser>(
          "/me",
          {},
          { includeAuth: false },
        );
        setCurrentUser(devUser);
        setAuthMessage(
          "저장된 로그인 정보가 만료되어 개발 모드 사용자로 전환했습니다.",
        );
        return;
      }
      setCurrentUser(null);
      setAuthMessage(getErrorMessage(error, "현재 사용자 정보를 불러오지 못했습니다."));
    } finally {
      setIsLoadingCurrentUser(false);
    }
  }

  async function handleAuthSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const email = authEmail.trim();
    const password = authPassword;
    if (!email || !password) {
      setAuthMessage("이메일과 비밀번호를 입력해 주세요.");
      return;
    }
    if (authMode === "register" && password.length < 8) {
      setAuthMessage("회원가입 비밀번호는 8자 이상이어야 합니다.");
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
      setCurrentUser(response.user);
      setAuthPassword("");
      setAuthMessage(
        authMode === "login"
          ? "로그인했습니다."
          : "회원가입이 완료되었습니다.",
      );
      await refreshUserScopedData();
    } catch (error) {
      const errorMessage = getErrorMessage(
        error,
        "이메일 또는 비밀번호가 올바르지 않습니다.",
      );
      setAuthMessage(
        errorMessage.includes("(401)")
          ? "이메일 또는 비밀번호가 올바르지 않습니다."
          : errorMessage,
      );
    } finally {
      setIsSubmittingAuth(false);
    }
  }

  async function handleLogout() {
    clearAccessToken();
    setAuthPassword("");
    setAuthMessage("로그아웃했습니다. 개발 모드 데이터로 전환합니다.");
    await loadCurrentUser();
    await refreshUserScopedData();
  }

  function clearClassificationDraft() {
    window.localStorage.removeItem(CLASSIFICATION_DRAFT_KEY);
    setPendingClassificationDraft(null);
    setClassificationDraftSavedAt("");
  }

  function restoreClassificationDraft() {
    const draft = pendingClassificationDraft;
    if (!draft) {
      return;
    }

    const restoredDeckId = decks.some((deck) => String(deck.id) === draft.deck_id)
      ? draft.deck_id
      : defaultDeck
        ? String(defaultDeck.id)
        : "";
    setText(draft.text);
    setSelectedSaveDeckId(restoredDeckId);
    setIncludeKnown(draft.include_known);
    setTokens(draft.tokens);
    setCurrentAnalyzeCardIndex(draft.current_index);
    setShowAllAnalyzeResults(false);
    setClassificationDraftSavedAt(draft.saved_at);
    setPendingClassificationDraft(null);
    setActiveTab("analyze");
    void loadDeckVocabItemsForCoverage(restoredDeckId);
  }

  async function loadDecks() {
    try {
      const data = await requestJson<DecksResponse>("/decks");
      setDecks(data.items);
      const defaultDeck =
        data.items.find((deck) => deck.name === "기본 단어장") ?? data.items[0];
      setSelectedSaveDeckId((currentDeckId) =>
        data.items.some((deck) => String(deck.id) === currentDeckId)
          ? currentDeckId
          : defaultDeck
            ? String(defaultDeck.id)
            : "",
      );
      setReadingSelectedDeckId((currentDeckId) =>
        data.items.some((deck) => String(deck.id) === currentDeckId)
          ? currentDeckId
          : defaultDeck
            ? String(defaultDeck.id)
            : "",
      );
    } catch (error) {
      setDeckMessage(getErrorMessage(error, "덱 목록을 불러오지 못했습니다."));
    }
  }

  async function handleAnalyze(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    if (!text.trim()) {
      setMessage("분석할 일본어 원문을 입력해 주세요.");
      setTokens([]);
      setCurrentAnalyzeCardIndex(0);
      setShowAllAnalyzeResults(false);
      clearClassificationDraft();
      return;
    }

    setIsAnalyzing(true);
    setMessage("");

    try {
      const response = await apiFetch("/analyze", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          text,
          deck_id: selectedSaveDeckId ? Number(selectedSaveDeckId) : null,
          include_known: includeKnown,
        }),
      });

      if (!response.ok) {
        throw new Error(`분석 요청에 실패했습니다. (${response.status})`);
      }

      const data = (await response.json()) as AnalyzeResponse;
      setTokens(
        data.tokens.map((token) => ({
          ...token,
          status: "unclassified",
          isClassified: false,
        })),
      );
      setIgnoredTokenCount(data.ignored_token_count || 0);
      setCurrentAnalyzeCardIndex(0);
      setShowAllAnalyzeResults(false);
      setPendingClassificationDraft(null);
      void loadDeckVocabItemsForCoverage(selectedSaveDeckId);
    } catch (error) {
      setMessage(getErrorMessage(error, "분석 중 알 수 없는 오류가 발생했습니다."));
      setTokens([]);
      setIgnoredTokenCount(0);
      setCurrentAnalyzeCardIndex(0);
      setShowAllAnalyzeResults(false);
    } finally {
      setIsAnalyzing(false);
    }
  }

  async function saveSelectedTokens() {
    const selectedTokens = tokens.filter(
      (token) =>
        token.status === "unknown" ||
        token.status === "uncertain" ||
        token.status === "known",
    );
    if (selectedTokens.length === 0) {
      setMessage("저장할 단어를 분류해 주세요.");
      return;
    }

    setIsSaving(true);
    setMessage("");

    try {
      await Promise.all(
        selectedTokens.map((token) =>
          requestJson<VocabItem>("/vocab-items", {
            method: "POST",
            body: JSON.stringify({
              ...token,
              deck_id: selectedSaveDeckId ? Number(selectedSaveDeckId) : null,
            }),
          }),
        ),
      );
      const unknownCount = selectedTokens.filter(
        (token) => token.status === "unknown",
      ).length;
      const uncertainCount = selectedTokens.filter(
        (token) => token.status === "uncertain",
      ).length;
      const knownCount = selectedTokens.filter(
        (token) => token.status === "known",
      ).length;
      setMessage(
        `완벽히 아는 단어 ${knownCount}개, 헷갈리는 단어 ${uncertainCount}개, 모르는 단어 ${unknownCount}개를 저장했습니다.`,
      );
      clearClassificationDraft();
      setTokens([]);
      setCurrentAnalyzeCardIndex(0);
      setShowAllAnalyzeResults(false);
      await loadVocabItems();
    } catch (error) {
      setMessage(getErrorMessage(error, "단어 저장 중 오류가 발생했습니다."));
    } finally {
      setIsSaving(false);
    }
  }

  async function loadVocabItems(deckId: string = selectedVocabDeckId) {
    setIsLoadingVocab(true);
    setVocabMessage("");

    try {
      const params = new URLSearchParams();
      if (deckId !== "all") {
        params.set("deck_id", deckId);
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
      setVocabItems(data.items);
      setHasLoadedVocab(true);
    } catch (error) {
      setVocabMessage(
        getErrorMessage(error, "단어장 목록을 불러오지 못했습니다."),
      );
    } finally {
      setIsLoadingVocab(false);
    }
  }

  function handleSelectedSaveDeckChange(deckId: string) {
    setSelectedSaveDeckId(deckId);
    if (tokens.length > 0) {
      void loadDeckVocabItemsForCoverage(deckId);
    }
  }

  async function loadDeckVocabItemsForCoverage(deckId: string) {
    if (!deckId) {
      setDeckVocabItems([]);
      return;
    }

    try {
      const data = await requestJson<VocabItemsResponse>(
        `/vocab-items?deck_id=${deckId}`,
      );
      setDeckVocabItems(data.items);
    } catch {
      setDeckVocabItems([]);
    }
  }

  // Reading tab: analyzes text with include_known always true so already-known
  // words still render in the natural text flow (just muted), then derives
  // each token's live status from the selected deck's saved vocab items so
  // colors match the deck the user picked. The original text only ever lives
  // in this component's React state (and the classification draft in
  // localStorage) -- it is never sent anywhere for server-side storage.
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

    setIsReadingAnalyzing(true);
    setReadingMessage("");
    setRecentlySavedVocabItemIds([]);
    setCurrentSelectedTokenKey(null);
    setIsReadingSessionRestored(false);
    setReadingAnalyzeProgress({ current: 0, total: chunks.length });

    const abortController = new AbortController();
    readingAnalyzeAbortRef.current = abortController;

    try {
      const [outcome, deckVocabResponse] = await Promise.all([
        analyzeLongTextInChunks(
          chunks,
          async (chunkText, signal) => {
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
              throw new Error(`분석 요청에 실패했습니다. (${response.status})`);
            }
            return (await response.json()) as AnalyzeResponse;
          },
          {
            signal: abortController.signal,
            onProgress: (progress) => setReadingAnalyzeProgress(progress),
          },
        ),
        requestJson<VocabItemsResponse>(`/vocab-items?deck_id=${deckId}`),
      ]);

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
          `분석에 실패했습니다. 잠시 후 다시 시도해주세요. (${outcome.failedChunkCount}/${outcome.totalChunkCount} 조각 실패)`,
        );
        setReadingTokens([]);
        return;
      }

      const derivedTokens = deriveReadingTokens(outcome.tokens, deckItems, deckId);

      setReadingTokens(derivedTokens);
      setReadingDeckVocabItems(deckItems);
      setAnalyzedReadingText(analyzeText);
      setIsReadingTextCollapsed(true);

      if (outcome.failedChunkCount > 0) {
        setReadingMessage(
          `전체 ${outcome.totalChunkCount}조각 중 ${outcome.failedChunkCount}개 구간 분석에 실패했습니다. 나머지는 정상적으로 분석되었습니다. 실패한 구간은 다시 분석해 주세요.`,
        );
      } else if (chunks.length > 1) {
        setReadingMessage(
          `긴 원문을 ${chunks.length}조각으로 나눠 분석을 완료했습니다.`,
        );
      }
    } catch (error) {
      setReadingMessage(
        `분석에 실패했습니다. 잠시 후 다시 시도해주세요. (${getErrorMessage(error, "알 수 없는 오류")})`,
      );
      setReadingTokens([]);
    } finally {
      setIsReadingAnalyzing(false);
      setReadingAnalyzeProgress(null);
      readingAnalyzeAbortRef.current = null;
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
    try {
      const deckVocabResponse = await requestJson<VocabItemsResponse>(
        `/vocab-items?deck_id=${deckId}`,
      );
      const deckItems = deckVocabResponse.items;
      setReadingDeckVocabItems(deckItems);
      setReadingTokens(deriveReadingTokens(baseTokens, deckItems, deckId));
    } catch {
      // Restored tokens still render fine with their last-known status;
      // this refresh is a nice-to-have, not required for the tab to work.
    }
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
    setReadingText("");
    setAnalyzedReadingText("");
    setReadingTokens([]);
    setReadingDeckVocabItems([]);
    setReadingMessage("현재 읽기 작업을 초기화했습니다.");
    setReadingStorageWarning("");
    setIsReadingTextCollapsed(false);
    setRecentlySavedVocabItemIds([]);
    setCurrentSelectedTokenKey(null);
    setIsReadingSessionRestored(false);
    clearReadingSession();
  }

  // Sends the analyze-tab's current text/deck straight into reading-tab state
  // (in-memory only) and kicks off the same read-only analysis there -- no
  // localStorage/server hop needed since both tabs live in one page.
  function viewCurrentTextInReadingTab() {
    setReadingText(text);
    setReadingSelectedDeckId(selectedSaveDeckId);
    setActiveTab("reading");
    void performReadingAnalyze(text, selectedSaveDeckId);
  }

  // Reading tab persists status changes immediately (no separate save step).
  async function handleReadingStatusChange(index: number, status: TokenStatus) {
    const token = readingTokens[index];
    if (!token || !readingSelectedDeckId) {
      return;
    }

    setReadingTokens((current) =>
      current.map((item, itemIndex) =>
        itemIndex === index ? { ...item, status, isClassified: true } : item,
      ),
    );

    try {
      const saved = await persistReadingToken(
        token,
        Number(readingSelectedDeckId),
        status,
        readingDeckVocabItems,
      );
      setReadingDeckVocabItems((current) => {
        const exists = current.some((item) => item.id === saved.id);
        return exists
          ? current.map((item) => (item.id === saved.id ? saved : item))
          : [...current, saved];
      });
    } catch (error) {
      setReadingMessage(
        getErrorMessage(
          error,
          "단어 상태 저장에 실패했습니다. 잠시 후 다시 시도해주세요.",
        ),
      );
    }
  }

  // "이 텍스트 학습 요약" 패널의 일괄 저장 버튼들. 대상 단어 목록/저장할
  // status는 resolveReadingSaveTargets가 결정하고, 여기서는 병렬로 저장한
  // 뒤 성공/실패 개수를 메시지로 보여준다.
  async function saveReadingTokensBatch(mode: ReadingSaveMode) {
    if (!readingSelectedDeckId || isSavingReadingBatch) {
      return;
    }

    const targets = resolveReadingSaveTargets(
      readingTokens,
      readingDeckVocabItems,
      readingSelectedDeckId,
      mode,
    );

    if (targets.length === 0) {
      setReadingMessage(
        "저장 가능한 단어가 없습니다. 이미 학습 중인 단어일 수 있습니다.",
      );
      return;
    }

    // Words that are already saved with the exact target status and already
    // have a context sentence need no API call at all -- skip them and
    // report them separately instead of re-sending an unchanged PATCH.
    const toPersist = targets.filter((target) => !target.alreadySaved);
    const skipped = targets.filter((target) => target.alreadySaved);

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
      const skippedIndexes = new Set(skipped.map((target) => target.index));
      const statusByIndex = new Map(
        succeeded.map(({ index, item }) => [index, item.status] as const),
      );
      setReadingTokens((current) =>
        current.map((item, itemIndex) => {
          const newStatus = statusByIndex.get(itemIndex);
          if (newStatus) {
            return { ...item, status: newStatus, isClassified: true };
          }
          return skippedIndexes.has(itemIndex)
            ? { ...item, isClassified: true }
            : item;
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
      parts.push(`단어 ${succeeded.length}개를 저장했습니다`);
    }
    if (skipped.length > 0) {
      parts.push(`이미 저장된 단어 ${skipped.length}개는 건너뛰었습니다`);
    }
    if (failureCount > 0) {
      parts.push(`${failureCount}개는 저장하지 못했습니다. 잠시 후 다시 시도해주세요`);
    }
    if (parts.length === 0) {
      parts.push("저장할 단어가 없습니다");
    }
    setReadingMessage(`${parts.join(". ")}.`);
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
    setHasLoadedVocab(true);
    void loadVocabItems(readingSelectedDeckId);
    void loadCustomTerms(readingSelectedDeckId);
  }

  async function loadCustomTerms(deckId: string = selectedVocabDeckId) {
    try {
      const query = deckId !== "all" ? `?deck_id=${deckId}` : "";
      const data = await requestJson<CustomTermsResponse>(
        `/custom-terms${query}`,
      );
      setCustomTerms(data.items);
    } catch (error) {
      setVocabMessage(
        getErrorMessage(error, "사용자 정의 용어를 불러오지 못했습니다."),
      );
    }
  }

  async function loadStudyStats(deckId: string = selectedStudyDeckId) {
    setIsLoadingStudyStats(true);
    setStudyStatsMessage("");

    try {
      const query = deckId !== "all" ? `?deck_id=${deckId}` : "";
      const data = await requestJson<StatsResponse>(`/stats${query}`);
      setStudyStats(data);
    } catch (error) {
      setStudyStatsMessage(
        getErrorMessage(error, "학습 통계를 불러오지 못했습니다."),
      );
    } finally {
      setIsLoadingStudyStats(false);
    }
  }

  async function loadInfoStats() {
    setIsLoadingInfoStats(true);
    setInfoStatsMessage("");

    try {
      const data = await requestJson<StatsResponse>("/stats");
      setInfoStats(data);
    } catch (error) {
      setInfoStatsMessage(
        getErrorMessage(error, "전체 학습 통계를 불러오지 못했습니다."),
      );
    } finally {
      setIsLoadingInfoStats(false);
    }
  }

  async function loadSharedDecks() {
    setIsLoadingSharedDecks(true);
    setSharedDeckMessage("");

    try {
      const data = await requestJson<SharedDeckSummary[]>("/shared-decks");
      setSharedDecks(data);
      if (
        selectedSharedDeckId !== null &&
        !data.some((deck) => deck.id === selectedSharedDeckId)
      ) {
        setSelectedSharedDeckId(null);
        setSelectedSharedDeck(null);
      }
    } catch (error) {
      setSharedDeckMessage(
        getErrorMessage(error, "공유 덱 목록을 불러오지 못했습니다."),
      );
    } finally {
      setIsLoadingSharedDecks(false);
    }
  }

  async function loadSharedDeckDetail(sharedDeckId: number) {
    if (selectedSharedDeckId === sharedDeckId && selectedSharedDeck) {
      closeSharedDeckDetail();
      return;
    }
    setSelectedSharedDeckId(sharedDeckId);
    setIsLoadingSharedDeckDetail(true);
    setSharedDeckMessage("");

    try {
      const data = await requestJson<SharedDeckDetail>(
        `/shared-decks/${sharedDeckId}`,
      );
      setSelectedSharedDeck(data);
    } catch (error) {
      setSharedDeckMessage(
        getErrorMessage(error, "공유 덱 상세 정보를 불러오지 못했습니다."),
      );
    } finally {
      setIsLoadingSharedDeckDetail(false);
    }
  }

  function closeSharedDeckDetail() {
    setSelectedSharedDeckId(null);
    setSelectedSharedDeck(null);
    setIsLoadingSharedDeckDetail(false);
  }

  function goToVocabTab() {
    setActiveTab("vocab");
    setHasLoadedVocab(true);
    void loadVocabItems(selectedVocabDeckId);
    void loadCustomTerms(selectedVocabDeckId);
  }

  async function publishCurrentDeck() {
    if (selectedVocabDeckId === "all") {
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
        `${result.title} 덱을 공유 덱으로 등록했습니다. 단어 수 ${result.vocab_count}개, 용어 수 ${result.custom_term_count}개를 복사했습니다.`,
      );
      await loadSharedDecks();
    } catch (error) {
      setDeckMessage(getErrorMessage(error, "공유 덱 등록에 실패했습니다."));
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
      const totalImportedCount =
        result.imported_vocab_count + result.imported_custom_term_count;
      setSharedDeckMessage(
        `${withObjectParticle(sourceTitle)} 내 단어장으로 가져왔습니다. 단어 ${totalImportedCount}개를 담았습니다. 단어장 탭에서 확인할 수 있습니다.`,
      );
      setImportedSharedDeckId(sharedDeckId);
      const importedDeckId = String(result.deck_id);
      setSelectedVocabDeckId(importedDeckId);
      setSelectedSaveDeckId(importedDeckId);
      await loadDecks();
      await loadVocabItems(importedDeckId);
      await loadCustomTerms(importedDeckId);
      await loadSharedDecks();
    } catch {
      setSharedDeckMessage(
        "공유덱 가져오기에 실패했습니다. 잠시 후 다시 시도해주세요.",
      );
    } finally {
      setImportingSharedDeckId(null);
    }
  }

  async function unpublishSharedDeck(sharedDeckId: number) {
    if (
      !window.confirm(
        "이 공유덱을 공유 목록에서 내릴까요? 이미 다른 사용자가 가져간 개인 덱은 삭제되지 않습니다.",
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
      setSharedDecks((currentDecks) =>
        currentDecks.filter((deck) => deck.id !== sharedDeckId),
      );
      if (selectedSharedDeckId === sharedDeckId) {
        closeSharedDeckDetail();
      }
      setSharedDeckMessage("공유덱을 공유 목록에서 내렸습니다.");
    } catch (error) {
      if (isHttpError(error, 403)) {
        setSharedDeckMessage("내가 올린 공유덱만 공유 취소할 수 있습니다.");
      } else if (isHttpError(error, 404)) {
        setSharedDeckMessage("이미 삭제되었거나 존재하지 않는 공유덱입니다.");
        setSharedDecks((currentDecks) =>
          currentDecks.filter((deck) => deck.id !== sharedDeckId),
        );
      } else {
        setSharedDeckMessage("공유 취소에 실패했습니다.");
      }
    } finally {
      setUnpublishingSharedDeckId(null);
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
      setSelectedSaveDeckId(String(deck.id));
      setNewDeckName("");
      setNewDeckDescription("");
      setDeckMessage("덱을 저장했습니다.");
    } catch (error) {
      setDeckMessage(getErrorMessage(error, "덱 생성에 실패했습니다."));
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
      setDeckMessage(getErrorMessage(error, "덱 삭제에 실패했습니다."));
    }
  }

  async function changeVocabDeck(deckId: string) {
    setSelectedVocabDeckId(deckId);
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
      setVocabMessage(getErrorMessage(error, "단어 추가에 실패했습니다."));
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
        getErrorMessage(error, "사용자 정의 용어 추가에 실패했습니다."),
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
        getErrorMessage(error, "사용자 정의 용어 수정에 실패했습니다."),
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
        getErrorMessage(error, "사용자 정의 용어 삭제에 실패했습니다."),
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
      setVocabMessage(getErrorMessage(error, "단어 수정에 실패했습니다."));
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
  function applyUpdatedVocabItemEverywhere(updated: VocabItem) {
    const replaceIfMatch = (item: VocabItem) =>
      item.id === updated.id ? updated : item;
    setVocabItems((current) => current.map(replaceIfMatch));
    setDeckVocabItems((current) => current.map(replaceIfMatch));
    setReadingDeckVocabItems((current) => current.map(replaceIfMatch));
    setStudyItems((current) => current.map(replaceIfMatch));
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
      applyUpdatedVocabItemEverywhere(updated);
      setMeaningEditItemId(null);
      setMeaningEditDraft("");
      setMeaningEditMessage("");
    } catch (error) {
      setMeaningEditMessage(getErrorMessage(error, "뜻 수정에 실패했습니다."));
    } finally {
      setIsSavingMeaningEdit(false);
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
      setFeedbackMessage("신고가 접수되었습니다. 사전 품질 개선에 참고됩니다.");
    } catch (error) {
      setFeedbackMessage(getErrorMessage(error, "신고 접수에 실패했습니다."));
    } finally {
      setIsSubmittingFeedback(false);
    }
  }

  function openAppFeedback() {
    setIsAppFeedbackOpen(true);
    setAppFeedbackCategory("bug");
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
      setAppFeedbackResultMessage("피드백이 접수되었습니다. 감사합니다.");
    } catch (error) {
      setAppFeedbackResultMessage(
        getErrorMessage(error, "피드백 접수에 실패했습니다. 잠시 후 다시 시도해주세요."),
      );
    } finally {
      setIsSubmittingAppFeedback(false);
    }
  }

  function updateTokenStatus(index: number, status: TokenStatus) {
    setTokens((currentTokens) =>
      currentTokens.map((token, tokenIndex) =>
        tokenIndex === index ? { ...token, status, isClassified: true } : token,
      ),
    );
  }

  function classifyCurrentToken(status: TokenStatus) {
    setTokens((currentTokens) =>
      currentTokens.map((token, tokenIndex) =>
        tokenIndex === currentAnalyzeCardIndex
          ? { ...token, status, isClassified: true }
          : token,
      ),
    );
    setCurrentAnalyzeCardIndex((index) => Math.min(index + 1, tokens.length));
  }

  function moveToPreviousAnalyzeCard() {
    setCurrentAnalyzeCardIndex((index) => Math.max(index - 1, 0));
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
      setVocabMessage(getErrorMessage(error, "상태 변경에 실패했습니다."));
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
      setVocabMessage(getErrorMessage(error, "삭제에 실패했습니다."));
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
    if (selectedVocabDeckId === "all") {
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
        getErrorMessage(error, "덱 공유 파일 내보내기에 실패했습니다."),
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
      setSelectedSaveDeckId(String(result.deck_id));
      await loadVocabItems(String(result.deck_id));
      await loadCustomTerms(String(result.deck_id));
      setVocabMessage(
        `${result.deck_name} 덱을 만들고 단어 ${result.imported_vocab_count}개, 사용자 용어 ${result.imported_custom_term_count}개를 가져왔습니다.`,
      );
    } catch (error) {
      setVocabMessage(
        getErrorMessage(error, "덱 공유 파일 가져오기에 실패했습니다."),
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
        selectedVocabDeckId !== "all" ? `?deck_id=${selectedVocabDeckId}` : "";
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
      setVocabMessage(getErrorMessage(error, "CSV 다운로드에 실패했습니다."));
    } finally {
      setIsExportingCsv(false);
    }
  }

  function getDeckDisplayName(deckId: string) {
    if (deckId === "all") {
      return "전체 단어장";
    }
    return decks.find((deck) => String(deck.id) === deckId)?.name ?? "선택한 덱";
  }

  async function fetchStudyItems(deckId: string, mode: StudyMode) {
    const baseParams = new URLSearchParams();
    if (deckId !== "all") {
      baseParams.set("deck_id", deckId);
    }

    if (mode === "today") {
      const query = baseParams.toString() ? `?${baseParams.toString()}` : "";
      const data = await requestJson<StudyItemsResponse>(`/study-items${query}`);
      return data.items;
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
      return [...unknownItems, ...uncertainItems];
    }

    if (mode === "new") {
      const params = new URLSearchParams(baseParams);
      params.set("sort", "created_asc");
      const data = await requestJson<VocabItemsResponse>(
        `/vocab-items?${params.toString()}`,
      );
      return data.items.filter((item) => !item.last_reviewed_at);
    }

    if (mode === "recent") {
      if (recentlySavedVocabItemIds.length === 0) {
        return [];
      }
      const data = await requestJson<VocabItemsResponse>(
        `/vocab-items?${baseParams.toString()}`,
      );
      const recentIds = new Set(recentlySavedVocabItemIds);
      return data.items.filter((item) => recentIds.has(item.id));
    }

    const params = new URLSearchParams(baseParams);
    params.set("status", mode);
    params.set("sort", "next_review_asc");
    const data = await requestJson<VocabItemsResponse>(
      `/vocab-items?${params.toString()}`,
    );
    return data.items;
  }

  function getEmptyStudyMessage(mode: StudyMode, deckId: string) {
    const deckName = getDeckDisplayName(deckId);
    if (mode === "today") {
      return `${deckName}에는 오늘 복습할 단어가 없습니다.`;
    }
    if (mode === "uncertain") {
      return `${deckName}에 헷갈리는 단어가 없습니다.`;
    }
    if (mode === "unknown") {
      return `${deckName}에 모르는 단어가 없습니다.`;
    }
    if (mode === "new") {
      return "새로 학습할 단어가 없습니다.";
    }
    if (mode === "recent") {
      return "방금 저장한 단어를 찾을 수 없습니다.";
    }
    return `${deckName}에 학습할 모르는 단어와 헷갈리는 단어가 없습니다.`;
  }

  async function startStudy(
    options: { deckId?: string; mode?: StudyMode } = {},
  ) {
    const deckId = options.deckId ?? selectedStudyDeckId;
    const mode = options.mode ?? studyMode;
    setIsLoadingStudy(true);
    setStudyMessage("");
    setStudyItems([]);
    setCurrentStudyIndex(0);
    setIsAnswerVisible(false);
    setSessionCounts(createEmptySessionCounts());
    setNextUpcomingReviewAt(null);
    answerShownAtRef.current = null;
    setHasStartedStudy(false);

    try {
      const items = await fetchStudyItems(deckId, mode);
      setStudyItems(items);
      setHasStartedStudy(true);
      if (items.length === 0) {
        setStudyMessage(getEmptyStudyMessage(mode, deckId));
      }
    } catch (error) {
      setStudyMessage(
        getErrorMessage(error, "학습 대상 단어를 불러오지 못했습니다."),
      );
    } finally {
      setIsLoadingStudy(false);
    }
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
    if (selectedVocabDeckId === "all") {
      setVocabMessage("학습할 특정 덱을 먼저 선택해 주세요.");
      return;
    }
    setSelectedStudyDeckId(selectedVocabDeckId);
    setActiveTab("study");
    void loadStudyStats(selectedVocabDeckId);
    void startStudy({ deckId: selectedVocabDeckId });
  }

  function goToVocabFromStudy() {
    setSelectedVocabDeckId(selectedStudyDeckId);
    setActiveTab("vocab");
    setHasLoadedVocab(true);
    void loadVocabItems(selectedStudyDeckId);
    void loadCustomTerms(selectedStudyDeckId);
  }

  function goToAnalyzeFromStudy() {
    setActiveTab("analyze");
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
      const updatedItem = await requestJson<VocabItem>(
        `/study-items/${currentItem.id}/review`,
        {
          method: "POST",
          body: JSON.stringify({ rating, response_time_ms: responseTimeMs }),
        },
      );
      setVocabItems((currentItems) =>
        currentItems.map((item) =>
          item.id === updatedItem.id ? updatedItem : item,
        ),
      );
      setSessionCounts((counts) => ({
        ...counts,
        [rating]: counts[rating] + 1,
      }));
      setNextUpcomingReviewAt((current) => {
        if (!updatedItem.next_review_at) {
          return current;
        }
        if (!current || updatedItem.next_review_at < current) {
          return updatedItem.next_review_at;
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
      setStudyMessage(getErrorMessage(error, "복습 결과 저장에 실패했습니다."));
    } finally {
      setIsReviewing(false);
    }
  }

  const currentStudyItem = studyItems[currentStudyIndex];
  const isStudyComplete =
    hasStartedStudy && studyItems.length > 0 && currentStudyIndex >= studyItems.length;

  // Same "not really signed in" check AccountPanel uses internally, lifted
  // up so the landing hero's CTAs can vary by auth state too.
  const isDevUser = !currentUser || currentUser.auth_provider === "dev";

  function scrollToAccountPanel() {
    document
      .getElementById("account-panel")
      ?.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  const currentScreenLabel =
    tabs.find((tab) => tab.key === activeTab)?.label ?? activeTab;

  return (
    <main className="page">
      <section className="workspace">
        <header className="header">
          <div>
            <h1>일본어 단어 분석</h1>
            <p>일본어 원문을 붙여넣고 학습할 단어 후보를 확인합니다.</p>
          </div>
          <button
            type="button"
            className="secondary-button compact-button header-feedback-button"
            onClick={openAppFeedback}
          >
            피드백
          </button>
        </header>

        {activeTab === "analyze" ? (
          <section className="landing-hero" aria-label="서비스 소개">
            <div className="landing-hero-copy">
              <h2 className="landing-hero-title">
                일본어 원문을 붙여넣으면,
                <br />
                모르는 단어만 골라 문맥 예문과 함께 복습합니다.
              </h2>
              <p className="landing-hero-subtitle">
                웹소설·원서·기사 속 일본어 단어를 자동으로 분석하고, 한국어
                뜻과 읽기를 확인한 뒤 SRS로 복습할 수 있습니다.
              </p>
              <div className="landing-hero-actions">
                <button
                  type="button"
                  onClick={() => void handleTabChange("reading")}
                >
                  {isDevUser ? "원문 분석 시작하기" : "읽기 탭으로 이동"}
                </button>
                <button
                  type="button"
                  className="secondary-button"
                  onClick={
                    isDevUser
                      ? scrollToAccountPanel
                      : () => void handleTabChange("study")
                  }
                >
                  {isDevUser ? "회원가입 · 로그인" : "오늘 복습하러 가기"}
                </button>
              </div>
              <p className="landing-trust-note">
                입력한 원문은 분석에만 사용되며, 원문 전체는 저장하지
                않습니다. 단어장에는 학습에 필요한 단어 정보와 짧은 문맥
                예문만 저장됩니다.
              </p>
            </div>

            <div className="landing-steps">
              <div className="landing-step-card">
                <span className="landing-step-number">1</span>
                <h3>원문 붙여넣기</h3>
                <p>읽고 싶은 일본어 문장을 붙여넣고 분석합니다.</p>
              </div>
              <div className="landing-step-card">
                <span className="landing-step-number">2</span>
                <h3>모르는 단어 저장</h3>
                <p>뜻과 읽기를 확인하고, 모르는 단어만 단어장에 저장합니다.</p>
              </div>
              <div className="landing-step-card">
                <span className="landing-step-number">3</span>
                <h3>문맥 예문으로 복습</h3>
                <p>단어가 나온 짧은 문장과 함께 SRS로 복습합니다.</p>
              </div>
            </div>

            <div className="landing-preview-grid">
              <div className="landing-preview-card">
                <strong>원문 분석</strong>
                <span>붙여넣은 문장에서 학습할 단어를 자동으로 추출합니다.</span>
              </div>
              <div className="landing-preview-card">
                <strong>상태별 단어 표시</strong>
                <span>아는/모르는/헷갈리는 단어를 색으로 구분해 보여줍니다.</span>
              </div>
              <div className="landing-preview-card">
                <strong>문맥 예문 SRS</strong>
                <span>단어가 나온 문장과 함께 복습 카드를 만듭니다.</span>
              </div>
              <div className="landing-preview-card">
                <strong>JLPT 추천 어휘 공유덱</strong>
                <span>레벨별 추천 단어 덱을 가져와 바로 학습합니다.</span>
              </div>
            </div>
          </section>
        ) : null}

        <AccountPanel
          user={currentUser}
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

        <nav className="tab-nav" aria-label="주요 기능">
          {tabs.map((tab) => (
            <button
              key={tab.key}
              type="button"
              className={activeTab === tab.key ? "tab active-tab" : "tab"}
              onClick={() => void handleTabChange(tab.key)}
            >
              {tab.label}
            </button>
          ))}
        </nav>

        {activeTab === "analyze" ? (
          <AnalyzeSection
            text={text}
            tokens={tokens}
            ignoredTokenCount={ignoredTokenCount}
            deckVocabItems={deckVocabItems}
            isAnalyzing={isAnalyzing}
            isSaving={isSaving}
            message={message}
            decks={decks}
            selectedDeckId={selectedSaveDeckId}
            includeKnown={includeKnown}
            currentCardIndex={currentAnalyzeCardIndex}
            showAllResults={showAllAnalyzeResults}
            pendingDraft={pendingClassificationDraft}
            draftSavedAt={classificationDraftSavedAt}
            onTextChange={setText}
            onSelectedDeckChange={handleSelectedSaveDeckChange}
            onIncludeKnownChange={setIncludeKnown}
            onAnalyze={handleAnalyze}
            onSaveSelected={() => void saveSelectedTokens()}
            onStatusChange={updateTokenStatus}
            onClassifyCurrent={classifyCurrentToken}
            onPreviousCard={moveToPreviousAnalyzeCard}
            onShowAllResultsChange={setShowAllAnalyzeResults}
            onRestoreDraft={restoreClassificationDraft}
            onDiscardDraft={clearClassificationDraft}
            onViewInReadingTab={viewCurrentTextInReadingTab}
          />
        ) : null}

        {activeTab === "reading" ? (
          <ReadingTab
            text={readingText}
            analyzedText={analyzedReadingText}
            tokens={readingTokens}
            vocabItems={readingDeckVocabItems}
            decks={decks}
            selectedDeckId={readingSelectedDeckId}
            isAnalyzing={isReadingAnalyzing}
            analyzeProgress={readingAnalyzeProgress}
            onCancelAnalyze={cancelReadingAnalyze}
            message={readingMessage}
            storageWarning={readingStorageWarning}
            isTextCollapsed={isReadingTextCollapsed}
            isSavingBatch={isSavingReadingBatch}
            canStartFromSaved={recentlySavedVocabItemIds.length > 0}
            isSessionRestored={isReadingSessionRestored}
            selectedTokenKey={currentSelectedTokenKey}
            onTextChange={setReadingText}
            onSelectedDeckChange={setReadingSelectedDeckId}
            onAnalyze={handleReadingAnalyze}
            onStatusChange={(index, status) =>
              void handleReadingStatusChange(index, status)
            }
            onToggleTextCollapsed={toggleReadingTextCollapsed}
            onSaveBatch={(mode) => void saveReadingTokensBatch(mode)}
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
            message={sharedDeckMessage}
            onRefresh={() => void loadSharedDecks()}
            onSelectDeck={(deckId) => void loadSharedDeckDetail(deckId)}
            onCloseDetail={closeSharedDeckDetail}
            onImportDeck={(deckId) => void importSharedDeckToMyDeck(deckId)}
            onUnpublishDeck={(deckId) => void unpublishSharedDeck(deckId)}
            onGoToVocab={goToVocabTab}
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
            decks={decks}
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
            onGoToAnalyze={goToAnalyzeFromStudy}
            onShowAnswer={() => {
              answerShownAtRef.current = Date.now();
              setIsAnswerVisible(true);
            }}
            onReview={(result) => void submitStudyReview(result)}
          />
        ) : null}

        {activeTab === "info" ? (
          <InfoSection
            stats={infoStats}
            isStatsLoading={isLoadingInfoStats}
            statsMessage={infoStatsMessage}
          />
        ) : null}
      </section>

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

type AccountPanelProps = {
  user: CurrentUser | null;
  authMode: "login" | "register";
  email: string;
  password: string;
  displayName: string;
  message: string;
  isLoadingUser: boolean;
  isSubmitting: boolean;
  onAuthModeChange: (mode: "login" | "register") => void;
  onEmailChange: (value: string) => void;
  onPasswordChange: (value: string) => void;
  onDisplayNameChange: (value: string) => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
  onLogout: () => void;
};

function AccountPanel({
  user,
  authMode,
  email,
  password,
  displayName,
  message,
  isLoadingUser,
  isSubmitting,
  onAuthModeChange,
  onEmailChange,
  onPasswordChange,
  onDisplayNameChange,
  onSubmit,
  onLogout,
}: AccountPanelProps) {
  const isDevUser = !user || user.auth_provider === "dev";

  return (
    <section id="account-panel" className="account-panel" aria-label="계정">
      <div className="account-summary">
        <div>
          <strong>{isDevUser ? "로그인하지 않은 개발 모드" : user.display_name}</strong>
          <span>
            {isLoadingUser
              ? "사용자 확인 중"
              : user
                ? `${user.email} · ${user.auth_provider}`
                : "사용자 정보를 불러오지 못했습니다."}
          </span>
        </div>
        {!isDevUser ? (
          <button type="button" className="secondary-button" onClick={onLogout}>
            로그아웃
          </button>
        ) : null}
      </div>

      {isDevUser ? (
        <form className="account-form" onSubmit={onSubmit}>
          <div className="account-mode">
            <button
              type="button"
              className={authMode === "login" ? "mode-button active-mode" : "mode-button"}
              onClick={() => onAuthModeChange("login")}
            >
              로그인
            </button>
            <button
              type="button"
              className={
                authMode === "register" ? "mode-button active-mode" : "mode-button"
              }
              onClick={() => onAuthModeChange("register")}
            >
              회원가입
            </button>
          </div>
          <label>
            이메일
            <input
              type="email"
              value={email}
              onChange={(event) => onEmailChange(event.target.value)}
              placeholder="test@example.com"
            />
          </label>
          <label>
            비밀번호
            <input
              type="password"
              value={password}
              onChange={(event) => onPasswordChange(event.target.value)}
              placeholder="8자 이상"
            />
          </label>
          {authMode === "register" ? (
            <label>
              표시 이름
              <input
                type="text"
                value={displayName}
                onChange={(event) => onDisplayNameChange(event.target.value)}
                placeholder="비우면 이메일 앞부분"
              />
            </label>
          ) : null}
          <button type="submit" className="primary-button" disabled={isSubmitting}>
            {isSubmitting
              ? "처리 중"
              : authMode === "login"
                ? "로그인"
                : "회원가입"}
          </button>
        </form>
      ) : null}

      {message ? <p className="account-message">{message}</p> : null}
    </section>
  );
}

async function requestJson<T>(
  path: string,
  init: RequestInit = {},
  options: { includeAuth?: boolean } = {},
): Promise<T> {
  const response = await apiFetch(path, init, options);

  if (!response.ok) {
    let detail = "";
    try {
      const data = (await response.json()) as { detail?: string };
      detail = data.detail ? ` ${data.detail}` : "";
    } catch {
      detail = "";
    }
    throw new ApiError(response.status, getHttpErrorMessage(response.status, detail));
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
  if (includeAuth && token && response.status === 401) {
    clearAccessToken();
  }
  return response;
}

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

function getErrorMessage(error: unknown, fallback: string) {
  return error instanceof Error ? error.message : fallback;
}

class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

function isHttpError(error: unknown, status: number) {
  return error instanceof ApiError && error.status === status;
}

function getHttpErrorMessage(status: number, detail: string) {
  const suffix = detail.trim() ? ` ${detail.trim()}` : "";
  if (status === 400) {
    return `요청 값을 확인해 주세요. (${status})${suffix}`;
  }
  if (status === 401) {
    return `로그인이 만료되었습니다. (${status})${suffix}`;
  }
  if (status === 404) {
    return `대상을 찾을 수 없습니다. (${status})${suffix}`;
  }
  if (status >= 500) {
    return `서버 오류가 발생했습니다. 잠시 후 다시 시도해 주세요. (${status})${suffix}`;
  }
  return `요청에 실패했습니다. (${status})${suffix}`;
}
