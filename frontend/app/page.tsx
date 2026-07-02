"use client";

import { FormEvent, useEffect, useState } from "react";

type TokenStatus = "unclassified" | "known" | "unknown";

type Token = {
  surface: string;
  base_form: string;
  reading: string;
  part_of_speech: string;
  normalized_form: string;
  meaning_ko: string;
  example_sentence: string;
};

type TokenWithStatus = Token & {
  status: TokenStatus;
};

type VocabItem = TokenWithStatus & {
  id: number;
  correct_count: number;
  wrong_count: number;
  last_reviewed_at: string | null;
  review_level: number;
  next_review_at: string | null;
  created_at: string;
  updated_at: string;
};

type AnalyzeResponse = {
  tokens: Token[];
};

type VocabItemsResponse = {
  items: VocabItem[];
};

type StudyItemsResponse = {
  items: VocabItem[];
};

type ReviewResult = "correct" | "wrong";

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL || "http://127.0.0.1:8000";

const statusLabels: Record<TokenStatus, string> = {
  unclassified: "미분류",
  known: "아는 단어",
  unknown: "모르는 단어",
};

export default function HomePage() {
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

  useEffect(() => {
    void loadVocabItems();
  }, []);

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
    } catch (error) {
      setVocabMessage(
        getErrorMessage(error, "단어장 목록을 불러오지 못했습니다."),
      );
    } finally {
      setIsLoadingVocab(false);
    }
  }

  async function updateTokenStatus(index: number, status: TokenStatus) {
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

        <form className="analyze-form" onSubmit={handleAnalyze}>
          <label htmlFor="source-text">원문</label>
          <textarea
            id="source-text"
            value={text}
            onChange={(event) => setText(event.target.value)}
            placeholder="彼は怠惰であることを自覚していた。"
            rows={8}
          />
          <div className="actions">
            <button type="submit" disabled={isAnalyzing}>
              {isAnalyzing ? "분석 중..." : "분석하기"}
            </button>
          </div>
        </form>

        {message ? <p className="message">{message}</p> : null}

        <section className="result-section" aria-live="polite">
          <div className="result-heading">
            <div>
              <h2>분석 결과</h2>
              <span>{tokens.length}개</span>
            </div>
            <button
              type="button"
              onClick={saveUnknownTokens}
              disabled={isSaving || tokens.length === 0}
            >
              {isSaving ? "저장 중..." : "모르는 단어 저장"}
            </button>
          </div>

          {tokens.length > 0 ? (
            <TokenTable
              tokens={tokens}
              onStatusChange={(index, status) =>
                void updateTokenStatus(index, status)
              }
            />
          ) : (
            <p className="empty">분석 결과가 아직 없습니다.</p>
          )}
        </section>

        <section className="result-section" aria-live="polite">
          <div className="result-heading">
            <div>
              <h2>학습 모드</h2>
              <span>
                {studyItems.length > 0
                  ? `${Math.min(currentStudyIndex + 1, studyItems.length)} / ${
                      studyItems.length
                    }`
                  : "0 / 0"}
              </span>
            </div>
            <button
              type="button"
              onClick={() => void startStudy()}
              disabled={isLoadingStudy}
            >
              {isLoadingStudy ? "불러오는 중..." : "학습 시작"}
            </button>
          </div>

          {studyMessage ? <p className="message">{studyMessage}</p> : null}

          {currentStudyItem && !isStudyComplete ? (
            <div className="study-card">
              <div className="study-progress">
                {currentStudyIndex + 1} / {studyItems.length}
              </div>
              <div className="study-front">
                {currentStudyItem.surface || currentStudyItem.base_form}
              </div>
              {isAnswerVisible ? (
                <>
                  <dl className="study-answer">
                    <div>
                      <dt>읽기</dt>
                      <dd>{currentStudyItem.reading || "-"}</dd>
                    </div>
                    <div>
                      <dt>뜻</dt>
                      <dd>{currentStudyItem.meaning_ko || "-"}</dd>
                    </div>
                    <div>
                      <dt>품사</dt>
                      <dd>{currentStudyItem.part_of_speech || "-"}</dd>
                    </div>
                    <div>
                      <dt>기본형</dt>
                      <dd>{currentStudyItem.base_form}</dd>
                    </div>
                    <div className="answer-example">
                      <dt>예문</dt>
                      <dd>{currentStudyItem.example_sentence || "-"}</dd>
                    </div>
                  </dl>
                  <div className="study-actions">
                    <button
                      type="button"
                      className="success-button"
                      onClick={() => void submitStudyReview("correct")}
                      disabled={isReviewing}
                    >
                      맞음
                    </button>
                    <button
                      type="button"
                      className="danger-button"
                      onClick={() => void submitStudyReview("wrong")}
                      disabled={isReviewing}
                    >
                      틀림
                    </button>
                  </div>
                </>
              ) : (
                <div className="study-actions">
                  <button type="button" onClick={() => setIsAnswerVisible(true)}>
                    정답 보기
                  </button>
                </div>
              )}
            </div>
          ) : null}

          {isStudyComplete ? (
            <div className="study-card complete-card">
              <h3>학습 완료</h3>
              <p>이번 세션 맞은 개수: {sessionCorrectCount}</p>
              <p>이번 세션 틀린 개수: {sessionWrongCount}</p>
              <p>오늘 복습을 완료했습니다.</p>
            </div>
          ) : null}
        </section>

        <section className="result-section" aria-live="polite">
          <div className="result-heading">
            <div>
              <h2>저장된 단어장</h2>
              <span>{vocabItems.length}개</span>
            </div>
            <div className="heading-actions">
              <button
                type="button"
                className="secondary-button"
                onClick={() => void downloadCsv()}
                disabled={isExportingCsv}
              >
                {isExportingCsv ? "다운로드 중..." : "CSV 다운로드"}
              </button>
              <button
                type="button"
                className="secondary-button"
                onClick={() => void loadVocabItems()}
                disabled={isLoadingVocab}
              >
                {isLoadingVocab ? "불러오는 중..." : "새로고침"}
              </button>
            </div>
          </div>

          {vocabMessage ? <p className="message">{vocabMessage}</p> : null}

          {vocabItems.length > 0 ? (
            <VocabTable
              items={vocabItems}
              onStatusChange={(itemId, status) =>
                void updateVocabStatus(itemId, status)
              }
              onDelete={(itemId) => void deleteVocabItem(itemId)}
            />
          ) : (
            <p className="empty">저장된 단어가 없습니다.</p>
          )}
        </section>
      </section>
    </main>
  );
}

function TokenTable({
  tokens,
  onStatusChange,
}: {
  tokens: TokenWithStatus[];
  onStatusChange: (index: number, status: TokenStatus) => void;
}) {
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th>단어</th>
            <th>기본형</th>
            <th>읽기</th>
            <th>품사</th>
            <th>뜻</th>
            <th>예문</th>
            <th>상태</th>
          </tr>
        </thead>
        <tbody>
          {tokens.map((token, index) => (
            <tr key={`${token.base_form}-${token.reading}-${index}`}>
              <td>{token.surface}</td>
              <td>{token.base_form}</td>
              <td>{token.reading}</td>
              <td>{token.part_of_speech}</td>
              <td>{token.meaning_ko || "-"}</td>
              <td>
                <span className="example-text">
                  {token.example_sentence || "-"}
                </span>
              </td>
              <td>
                <StatusSelect
                  value={token.status}
                  label={`${token.surface} 상태`}
                  onChange={(status) => onStatusChange(index, status)}
                />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function VocabTable({
  items,
  onStatusChange,
  onDelete,
}: {
  items: VocabItem[];
  onStatusChange: (itemId: number, status: TokenStatus) => void;
  onDelete: (itemId: number) => void;
}) {
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th>단어</th>
            <th>기본형</th>
            <th>읽기</th>
            <th>품사</th>
            <th>뜻</th>
            <th>예문</th>
            <th>상태</th>
            <th>맞음</th>
            <th>틀림</th>
            <th>레벨</th>
            <th>마지막 복습</th>
            <th>다음 복습</th>
            <th>삭제</th>
          </tr>
        </thead>
        <tbody>
          {items.map((item) => (
            <tr key={item.id}>
              <td>{item.surface}</td>
              <td>{item.base_form}</td>
              <td>{item.reading}</td>
              <td>{item.part_of_speech}</td>
              <td>{item.meaning_ko || "-"}</td>
              <td>
                <span className="example-text">
                  {item.example_sentence || "-"}
                </span>
              </td>
              <td>
                <StatusSelect
                  value={item.status}
                  label={`${item.surface} 저장 상태`}
                  onChange={(status) => onStatusChange(item.id, status)}
                />
              </td>
              <td>{item.correct_count}</td>
              <td>{item.wrong_count}</td>
              <td>{item.review_level}</td>
              <td>{formatDateTime(item.last_reviewed_at)}</td>
              <td>{formatNextReview(item.next_review_at)}</td>
              <td>
                <button
                  type="button"
                  className="danger-button"
                  onClick={() => onDelete(item.id)}
                >
                  삭제
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function StatusSelect({
  value,
  label,
  onChange,
}: {
  value: TokenStatus;
  label: string;
  onChange: (status: TokenStatus) => void;
}) {
  return (
    <select
      value={value}
      onChange={(event) => onChange(event.target.value as TokenStatus)}
      aria-label={label}
    >
      {Object.entries(statusLabels).map(([status, labelText]) => (
        <option key={status} value={status}>
          {labelText}
        </option>
      ))}
    </select>
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

function formatDateTime(value: string | null) {
  if (!value) {
    return "-";
  }

  return new Date(value).toLocaleString("ko-KR", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function formatNextReview(value: string | null) {
  if (!value) {
    return "다음 복습: 미정";
  }

  return `다음 복습: ${new Date(value).toLocaleDateString("ko-KR", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  })}`;
}
