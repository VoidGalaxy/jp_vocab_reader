"use client";

import { FormEvent, useEffect, useState } from "react";
import { AnalyzeSection } from "../components/AnalyzeSection";
import { InfoSection } from "../components/InfoSection";
import { StudySection } from "../components/StudySection";
import { VocabSection } from "../components/VocabSection";
import type {
  ReviewResult,
  Deck,
  Token,
  TokenStatus,
  TokenWithStatus,
  VocabFormData,
  VocabItem,
  VocabSort,
} from "../components/types";

type AnalyzeResponse = {
  tokens: Token[];
};

type VocabItemsResponse = {
  items: VocabItem[];
};

type StudyItemsResponse = {
  items: VocabItem[];
};

type DecksResponse = {
  items: Deck[];
};

type DeckDeleteResponse = {
  deleted_deck_id: number;
  deleted_vocab_count: number;
  message: string;
};

type TabKey = "analyze" | "vocab" | "study" | "info";
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

const tabs: Array<{ key: TabKey; label: string }> = [
  { key: "analyze", label: "분석" },
  { key: "vocab", label: "단어장" },
  { key: "study", label: "학습" },
  { key: "info", label: "정보" },
];

function createBlankVocabForm(deckId = ""): VocabFormData {
  return {
    surface: "",
    base_form: "",
    reading: "",
    part_of_speech: "",
    meaning_ko: "",
    example_sentence: "",
    context_explanation_ko: "",
    status: "unknown",
    deck_id: deckId,
  };
}

function vocabItemToForm(item: VocabItem): VocabFormData {
  return {
    surface: item.surface,
    base_form: item.base_form,
    reading: item.reading,
    part_of_speech: item.part_of_speech,
    meaning_ko: item.meaning_ko,
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
  const [editingItemId, setEditingItemId] = useState<number | null>(null);
  const [editVocabForm, setEditVocabForm] = useState<VocabFormData>(
    createBlankVocabForm(),
  );
  const [isCreatingDeck, setIsCreatingDeck] = useState(false);
  const [text, setText] = useState("");
  const [tokens, setTokens] = useState<TokenWithStatus[]>([]);
  const [vocabItems, setVocabItems] = useState<VocabItem[]>([]);
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [isAddingVocab, setIsAddingVocab] = useState(false);
  const [isUpdatingVocab, setIsUpdatingVocab] = useState(false);
  const [isLoadingVocab, setIsLoadingVocab] = useState(false);
  const [isExportingCsv, setIsExportingCsv] = useState(false);
  const [isLoadingStudy, setIsLoadingStudy] = useState(false);
  const [isReviewing, setIsReviewing] = useState(false);
  const [explainingItemId, setExplainingItemId] = useState<number | null>(null);
  const [message, setMessage] = useState("");
  const [vocabMessage, setVocabMessage] = useState("");
  const [deckMessage, setDeckMessage] = useState("");
  const [studyMessage, setStudyMessage] = useState("");
  const [studyItems, setStudyItems] = useState<VocabItem[]>([]);
  const [currentStudyIndex, setCurrentStudyIndex] = useState(0);
  const [isAnswerVisible, setIsAnswerVisible] = useState(false);
  const [sessionCorrectCount, setSessionCorrectCount] = useState(0);
  const [sessionWrongCount, setSessionWrongCount] = useState(0);
  const [hasStartedStudy, setHasStartedStudy] = useState(false);

  useEffect(() => {
    void loadDecks();
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
  }, [defaultVocabFormDeckId]);

  useEffect(() => {
    if (activeTab === "vocab" && hasLoadedVocab) {
      void loadVocabItems();
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

    setText(draft.text);
    setSelectedSaveDeckId(
      decks.some((deck) => String(deck.id) === draft.deck_id)
        ? draft.deck_id
        : defaultDeck
          ? String(defaultDeck.id)
          : "",
    );
    setIncludeKnown(draft.include_known);
    setTokens(draft.tokens);
    setCurrentAnalyzeCardIndex(draft.current_index);
    setShowAllAnalyzeResults(false);
    setClassificationDraftSavedAt(draft.saved_at);
    setPendingClassificationDraft(null);
    setActiveTab("analyze");
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
      const response = await fetch(`${API_BASE_URL}/analyze`, {
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
      setCurrentAnalyzeCardIndex(0);
      setShowAllAnalyzeResults(false);
      setPendingClassificationDraft(null);
    } catch (error) {
      setMessage(getErrorMessage(error, "분석 중 알 수 없는 오류가 발생했습니다."));
      setTokens([]);
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
      const response = await fetch(`${API_BASE_URL}/decks/${deckId}`, {
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

  function buildVocabPayload(form: VocabFormData) {
    return {
      surface: form.surface,
      base_form: form.base_form,
      reading: form.reading,
      part_of_speech: form.part_of_speech,
      meaning_ko: form.meaning_ko,
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
      const response = await fetch(`${API_BASE_URL}/vocab-items/${itemId}`, {
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

  async function downloadCsv() {
    setIsExportingCsv(true);
    setVocabMessage("CSV 파일을 준비하고 있습니다.");

    try {
      const query =
        selectedVocabDeckId !== "all" ? `?deck_id=${selectedVocabDeckId}` : "";
      const response = await fetch(`${API_BASE_URL}/vocab-items/export.csv${query}`);
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

  async function explainVocabItem(itemId: number) {
    setExplainingItemId(itemId);
    setVocabMessage("");

    try {
      const updatedItem = await requestJson<VocabItem>(
        `/vocab-items/${itemId}/explain`,
        {
          method: "POST",
        },
      );
      setVocabItems((currentItems) =>
        currentItems.map((item) => (item.id === itemId ? updatedItem : item)),
      );
      setStudyItems((currentItems) =>
        currentItems.map((item) => (item.id === itemId ? updatedItem : item)),
      );
      setVocabMessage("AI 문맥 설명을 저장했습니다.");
    } catch (error) {
      setVocabMessage(
        getErrorMessage(error, "AI 문맥 설명 생성에 실패했습니다."),
      );
    } finally {
      setExplainingItemId(null);
    }
  }

  async function startStudy() {
    setIsLoadingStudy(true);
    setStudyMessage("");
    setStudyItems([]);
    setCurrentStudyIndex(0);
    setIsAnswerVisible(false);
    setSessionCorrectCount(0);
    setSessionWrongCount(0);
    setHasStartedStudy(false);

    try {
      const query =
        selectedStudyDeckId !== "all" ? `?deck_id=${selectedStudyDeckId}` : "";
      const data = await requestJson<StudyItemsResponse>(`/study-items${query}`);
      setStudyItems(data.items);
      setHasStartedStudy(true);
      if (data.items.length === 0) {
        setStudyMessage("오늘 복습할 단어가 없습니다.");
      }
    } catch (error) {
      setStudyMessage(
        getErrorMessage(error, "학습 대상 단어를 불러오지 못했습니다."),
      );
    } finally {
      setIsLoadingStudy(false);
    }
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
            onSelectedDeckChange={setSelectedSaveDeckId}
            onIncludeKnownChange={setIncludeKnown}
            onAnalyze={handleAnalyze}
            onSaveSelected={() => void saveSelectedTokens()}
            onStatusChange={updateTokenStatus}
            onClassifyCurrent={classifyCurrentToken}
            onPreviousCard={moveToPreviousAnalyzeCard}
            onShowAllResultsChange={setShowAllAnalyzeResults}
            onRestoreDraft={restoreClassificationDraft}
            onDiscardDraft={clearClassificationDraft}
          />
        ) : null}

        {activeTab === "vocab" ? (
          <VocabSection
            items={vocabItems}
            isLoading={isLoadingVocab}
            isExportingCsv={isExportingCsv}
            explainingItemId={explainingItemId}
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
            onEditVocabFormChange={updateEditVocabForm}
            onStartEdit={startEditingVocabItem}
            onSaveEdit={() => void saveEditedVocabItem()}
            onCancelEdit={cancelEditingVocabItem}
            onRefresh={() => void loadVocabItems(selectedVocabDeckId)}
            onDownloadCsv={() => void downloadCsv()}
            onExplain={(itemId) => void explainVocabItem(itemId)}
            onStatusChange={(itemId, status) =>
              void updateVocabStatus(itemId, status)
            }
            onDelete={(itemId) => void deleteVocabItem(itemId)}
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
            correctCount={sessionCorrectCount}
            wrongCount={sessionWrongCount}
            decks={decks}
            selectedDeckId={selectedStudyDeckId}
            onSelectedDeckChange={setSelectedStudyDeckId}
            onStart={() => void startStudy()}
            onShowAnswer={() => setIsAnswerVisible(true)}
            onReview={(result) => void submitStudyReview(result)}
          />
        ) : null}

        {activeTab === "info" ? <InfoSection /> : null}
      </section>
    </main>
  );
}

async function requestJson<T>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...init.headers,
    },
  });

  if (!response.ok) {
    let detail = "";
    try {
      const data = (await response.json()) as { detail?: string };
      detail = data.detail ? ` ${data.detail}` : "";
    } catch {
      detail = "";
    }
    throw new Error(`요청에 실패했습니다. (${response.status})${detail}`);
  }

  return (await response.json()) as T;
}

function getErrorMessage(error: unknown, fallback: string) {
  return error instanceof Error ? error.message : fallback;
}
