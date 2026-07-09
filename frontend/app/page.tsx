"use client";

import { FormEvent, useEffect, useState } from "react";
import { AnalyzeSection } from "../components/AnalyzeSection";
import { getTokenGroupKey, getTokenStatus } from "../components/coverageUtils";
import { InfoSection } from "../components/InfoSection";
import { ReadingTab } from "../components/ReadingTab";
import { SharedDeckSection } from "../components/SharedDeckSection";
import { withObjectParticle } from "../components/shared";
import { StudySection } from "../components/StudySection";
import { VocabSection } from "../components/VocabSection";
import type {
  ReviewResult,
  Deck,
  QualityTag,
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
  { key: "shared", label: "공유" },
  { key: "info", label: "정보" },
];

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
  const [readingSelectedDeckId, setReadingSelectedDeckId] = useState("");
  const [readingTokens, setReadingTokens] = useState<TokenWithStatus[]>([]);
  const [readingDeckVocabItems, setReadingDeckVocabItems] = useState<VocabItem[]>(
    [],
  );
  const [isReadingAnalyzing, setIsReadingAnalyzing] = useState(false);
  const [readingMessage, setReadingMessage] = useState("");
  const [isReadingTextCollapsed, setIsReadingTextCollapsed] = useState(false);
  const [vocabItems, setVocabItems] = useState<VocabItem[]>([]);
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [isAddingVocab, setIsAddingVocab] = useState(false);
  const [isUpdatingVocab, setIsUpdatingVocab] = useState(false);
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
  const [sessionCorrectCount, setSessionCorrectCount] = useState(0);
  const [sessionWrongCount, setSessionWrongCount] = useState(0);
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
    setSessionCorrectCount(0);
    setSessionWrongCount(0);
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
  }, []);

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

    setIsReadingAnalyzing(true);
    setReadingMessage("");

    try {
      const [analyzeResponse, deckVocabResponse] = await Promise.all([
        apiFetch("/analyze", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            text: analyzeText,
            deck_id: Number(deckId),
            include_known: true,
          }),
        }),
        requestJson<VocabItemsResponse>(`/vocab-items?deck_id=${deckId}`),
      ]);

      if (!analyzeResponse.ok) {
        throw new Error(`분석 요청에 실패했습니다. (${analyzeResponse.status})`);
      }

      const analyzeData = (await analyzeResponse.json()) as AnalyzeResponse;
      const deckItems = deckVocabResponse.items;
      const derivedTokens: TokenWithStatus[] = analyzeData.tokens.map((token) => {
        const base: TokenWithStatus = {
          ...token,
          status: "unclassified",
          isClassified: false,
        };
        const status = getTokenStatus(base, deckItems, deckId);
        return { ...base, status, isClassified: status !== "unclassified" };
      });

      setReadingTokens(derivedTokens);
      setReadingDeckVocabItems(deckItems);
      setIsReadingTextCollapsed(true);
    } catch (error) {
      setReadingMessage(
        getErrorMessage(error, "분석 중 알 수 없는 오류가 발생했습니다."),
      );
      setReadingTokens([]);
    } finally {
      setIsReadingAnalyzing(false);
    }
  }

  function handleReadingAnalyze(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    void performReadingAnalyze(readingText, readingSelectedDeckId);
  }

  function toggleReadingTextCollapsed() {
    setIsReadingTextCollapsed((collapsed) => !collapsed);
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

  // Reading tab persists status changes immediately (no separate save step):
  // update the matching vocab item if the word is already saved in this
  // deck, otherwise create a new one -- reusing the same base_form ->
  // normalized_form -> surface matching policy as the coverage dashboard.
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

    const deckIdNumber = Number(readingSelectedDeckId);
    const key = getTokenGroupKey(token);
    const existing = readingDeckVocabItems.find(
      (item) => item.deck_id === deckIdNumber && getTokenGroupKey(item) === key,
    );

    try {
      if (existing) {
        const updated = await requestJson<VocabItem>(
          `/vocab-items/${existing.id}`,
          {
            method: "PATCH",
            body: JSON.stringify({ status }),
          },
        );
        setReadingDeckVocabItems((current) =>
          current.map((item) => (item.id === updated.id ? updated : item)),
        );
      } else {
        const created = await requestJson<VocabItem>("/vocab-items", {
          method: "POST",
          body: JSON.stringify({
            ...token,
            status,
            deck_id: deckIdNumber,
          }),
        });
        setReadingDeckVocabItems((current) => [...current, created]);
      }
    } catch (error) {
      setReadingMessage(
        getErrorMessage(error, "단어 상태 저장에 실패했습니다."),
      );
    }
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
    setSessionCorrectCount(0);
    setSessionWrongCount(0);
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

  async function submitStudyReview(result: ReviewResult) {
    const currentItem = studyItems[currentStudyIndex];
    if (!currentItem) {
      return;
    }

    setIsReviewing(true);
    setStudyMessage("");

    try {
      const updatedItem = await requestJson<VocabItem>(
        `/study-items/${currentItem.id}/review`,
        {
          method: "POST",
          body: JSON.stringify({ result }),
        },
      );
      setVocabItems((currentItems) =>
        currentItems.map((item) =>
          item.id === updatedItem.id ? updatedItem : item,
        ),
      );
      if (result === "correct") {
        setSessionCorrectCount((count) => count + 1);
      } else {
        setSessionWrongCount((count) => count + 1);
      }
      setCurrentStudyIndex((index) => index + 1);
      setIsAnswerVisible(false);
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

  return (
    <main className="page">
      <section className="workspace">
        <header className="header">
          <h1>일본어 단어 분석</h1>
          <p>일본어 원문을 붙여넣고 학습할 단어 후보를 확인합니다.</p>
        </header>

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
            tokens={readingTokens}
            decks={decks}
            selectedDeckId={readingSelectedDeckId}
            isAnalyzing={isReadingAnalyzing}
            message={readingMessage}
            isTextCollapsed={isReadingTextCollapsed}
            onTextChange={setReadingText}
            onSelectedDeckChange={setReadingSelectedDeckId}
            onAnalyze={handleReadingAnalyze}
            onStatusChange={(index, status) =>
              void handleReadingStatusChange(index, status)
            }
            onToggleTextCollapsed={toggleReadingTextCollapsed}
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
            correctCount={sessionCorrectCount}
            wrongCount={sessionWrongCount}
            decks={decks}
            selectedDeckId={selectedStudyDeckId}
            selectedDeckName={getDeckDisplayName(selectedStudyDeckId)}
            studyMode={studyMode}
            hasStarted={hasStartedStudy}
            onSelectedDeckChange={changeStudyDeck}
            onStudyModeChange={changeStudyMode}
            onStart={() => void startStudy()}
            onRestart={() => void startStudy()}
            onGoToVocab={goToVocabFromStudy}
            onGoToAnalyze={goToAnalyzeFromStudy}
            onShowAnswer={() => setIsAnswerVisible(true)}
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
    <section className="account-panel" aria-label="계정">
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
