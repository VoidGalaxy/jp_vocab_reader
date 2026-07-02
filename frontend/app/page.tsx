"use client";

import { FormEvent, useState } from "react";
import { AnalyzeSection } from "../components/AnalyzeSection";
import { InfoSection } from "../components/InfoSection";
import { StudySection } from "../components/StudySection";
import { VocabSection } from "../components/VocabSection";
import type {
  ReviewResult,
  Token,
  TokenStatus,
  TokenWithStatus,
  VocabItem,
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

type TabKey = "analyze" | "vocab" | "study" | "info";

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL || "http://127.0.0.1:8000";

const tabs: Array<{ key: TabKey; label: string }> = [
  { key: "analyze", label: "분석" },
  { key: "vocab", label: "단어장" },
  { key: "study", label: "학습" },
  { key: "info", label: "정보" },
];

export default function HomePage() {
  const [activeTab, setActiveTab] = useState<TabKey>("analyze");
  const [hasLoadedVocab, setHasLoadedVocab] = useState(false);
  const [text, setText] = useState("");
  const [tokens, setTokens] = useState<TokenWithStatus[]>([]);
  const [vocabItems, setVocabItems] = useState<VocabItem[]>([]);
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [isLoadingVocab, setIsLoadingVocab] = useState(false);
  const [isExportingCsv, setIsExportingCsv] = useState(false);
  const [isLoadingStudy, setIsLoadingStudy] = useState(false);
  const [isReviewing, setIsReviewing] = useState(false);
  const [message, setMessage] = useState("");
  const [vocabMessage, setVocabMessage] = useState("");
  const [studyMessage, setStudyMessage] = useState("");
  const [studyItems, setStudyItems] = useState<VocabItem[]>([]);
  const [currentStudyIndex, setCurrentStudyIndex] = useState(0);
  const [isAnswerVisible, setIsAnswerVisible] = useState(false);
  const [sessionCorrectCount, setSessionCorrectCount] = useState(0);
  const [sessionWrongCount, setSessionWrongCount] = useState(0);
  const [hasStartedStudy, setHasStartedStudy] = useState(false);

  async function handleTabChange(tab: TabKey) {
    setActiveTab(tab);
    if (tab === "vocab" && !hasLoadedVocab) {
      await loadVocabItems();
    }
  }

  async function handleAnalyze(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    if (!text.trim()) {
      setMessage("분석할 일본어 원문을 입력해 주세요.");
      setTokens([]);
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
        body: JSON.stringify({ text }),
      });

      if (!response.ok) {
        throw new Error(`분석 요청에 실패했습니다. (${response.status})`);
      }

      const data = (await response.json()) as AnalyzeResponse;
      setTokens(
        data.tokens.map((token) => ({
          ...token,
          status: "unclassified",
        })),
      );
    } catch (error) {
      setMessage(getErrorMessage(error, "분석 중 알 수 없는 오류가 발생했습니다."));
      setTokens([]);
    } finally {
      setIsAnalyzing(false);
    }
  }

  async function saveUnknownTokens() {
    const unknownTokens = tokens.filter((token) => token.status === "unknown");
    if (unknownTokens.length === 0) {
      setMessage("모르는 단어로 선택한 항목이 없습니다.");
      return;
    }

    setIsSaving(true);
    setMessage("");

    try {
      await Promise.all(
        unknownTokens.map((token) =>
          requestJson<VocabItem>("/vocab-items", {
            method: "POST",
            body: JSON.stringify(token),
          }),
        ),
      );
      setMessage(`${unknownTokens.length}개 단어를 저장했습니다.`);
      await loadVocabItems();
    } catch (error) {
      setMessage(getErrorMessage(error, "단어 저장 중 오류가 발생했습니다."));
    } finally {
      setIsSaving(false);
    }
  }

  async function loadVocabItems() {
    setIsLoadingVocab(true);
    setVocabMessage("");

    try {
      const data = await requestJson<VocabItemsResponse>("/vocab-items");
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

  function updateTokenStatus(index: number, status: TokenStatus) {
    setTokens((currentTokens) =>
      currentTokens.map((token, tokenIndex) =>
        tokenIndex === index ? { ...token, status } : token,
      ),
    );
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
      const updatedItem = await requestJson<VocabItem>(`/vocab-items/${itemId}`, {
        method: "PATCH",
        body: JSON.stringify({ status }),
      });
      setVocabItems((currentItems) =>
        currentItems.map((item) => (item.id === itemId ? updatedItem : item)),
      );
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
    } catch (error) {
      setVocabItems(previousItems);
      setVocabMessage(getErrorMessage(error, "삭제에 실패했습니다."));
    }
  }

  async function downloadCsv() {
    setIsExportingCsv(true);
    setVocabMessage("CSV 파일을 준비하고 있습니다.");

    try {
      const response = await fetch(`${API_BASE_URL}/vocab-items/export.csv`);
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
      const data = await requestJson<StudyItemsResponse>("/study-items");
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
            onTextChange={setText}
            onAnalyze={handleAnalyze}
            onSaveUnknown={() => void saveUnknownTokens()}
            onStatusChange={updateTokenStatus}
          />
        ) : null}

        {activeTab === "vocab" ? (
          <VocabSection
            items={vocabItems}
            isLoading={isLoadingVocab}
            isExportingCsv={isExportingCsv}
            message={vocabMessage}
            onRefresh={() => void loadVocabItems()}
            onDownloadCsv={() => void downloadCsv()}
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
    throw new Error(`요청에 실패했습니다. (${response.status})`);
  }

  return (await response.json()) as T;
}

function getErrorMessage(error: unknown, fallback: string) {
  return error instanceof Error ? error.message : fallback;
}
