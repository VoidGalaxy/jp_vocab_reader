"use client";

import { FormEvent, useState } from "react";

type Token = {
  surface: string;
  base_form: string;
  reading: string;
  part_of_speech: string;
  normalized_form: string;
  meaning_ko: string;
};

type TokenStatus = "unclassified" | "known" | "unknown";

type TokenWithStatus = Token & {
  status: TokenStatus;
};

type AnalyzeResponse = {
  tokens: Token[];
};

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
  const [isLoading, setIsLoading] = useState(false);
  const [message, setMessage] = useState("");

  async function handleAnalyze(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    if (!text.trim()) {
      setMessage("분석할 일본어 원문을 입력해 주세요.");
      setTokens([]);
      return;
    }

    setIsLoading(true);
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
      const errorMessage =
        error instanceof Error
          ? error.message
          : "분석 중 알 수 없는 오류가 발생했습니다.";
      setMessage(errorMessage);
      setTokens([]);
    } finally {
      setIsLoading(false);
    }
  }

  function updateStatus(index: number, status: TokenStatus) {
    setTokens((currentTokens) =>
      currentTokens.map((token, tokenIndex) =>
        tokenIndex === index ? { ...token, status } : token,
      ),
    );
  }

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
            <button type="submit" disabled={isLoading}>
              {isLoading ? "분석 중..." : "분석하기"}
            </button>
          </div>
        </form>

        {message ? <p className="message">{message}</p> : null}

        <section className="result-section" aria-live="polite">
          <div className="result-heading">
            <h2>분석 결과</h2>
            <span>{tokens.length}개</span>
          </div>

          {tokens.length > 0 ? (
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>단어</th>
                    <th>기본형</th>
                    <th>읽기</th>
                    <th>품사</th>
                    <th>뜻</th>
                    <th>상태</th>
                  </tr>
                </thead>
                <tbody>
                  {tokens.map((token, index) => (
                    <tr key={`${token.base_form}-${index}`}>
                      <td>{token.surface}</td>
                      <td>{token.base_form}</td>
                      <td>{token.reading}</td>
                      <td>{token.part_of_speech}</td>
                      <td>{token.meaning_ko || "-"}</td>
                      <td>
                        <select
                          value={token.status}
                          onChange={(event) =>
                            updateStatus(index, event.target.value as TokenStatus)
                          }
                          aria-label={`${token.surface} 상태`}
                        >
                          {Object.entries(statusLabels).map(([value, label]) => (
                            <option key={value} value={value}>
                              {label}
                            </option>
                          ))}
                        </select>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <p className="empty">분석 결과가 아직 없습니다.</p>
          )}
        </section>
      </section>
    </main>
  );
}
