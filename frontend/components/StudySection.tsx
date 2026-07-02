"use client";

import type { ReviewResult, VocabItem } from "./types";

type StudySectionProps = {
  items: VocabItem[];
  currentItem?: VocabItem;
  currentIndex: number;
  isComplete: boolean;
  isAnswerVisible: boolean;
  isLoading: boolean;
  isReviewing: boolean;
  message: string;
  correctCount: number;
  wrongCount: number;
  onStart: () => void;
  onShowAnswer: () => void;
  onReview: (result: ReviewResult) => void;
};

export function StudySection({
  items,
  currentItem,
  currentIndex,
  isComplete,
  isAnswerVisible,
  isLoading,
  isReviewing,
  message,
  correctCount,
  wrongCount,
  onStart,
  onShowAnswer,
  onReview,
}: StudySectionProps) {
  return (
    <section className="tab-panel" aria-live="polite">
      <div className="result-heading">
        <div>
          <h2>학습 모드</h2>
          <span>
            {items.length > 0
              ? `${Math.min(currentIndex + 1, items.length)} / ${items.length}`
              : "0 / 0"}
          </span>
        </div>
        <button type="button" onClick={onStart} disabled={isLoading}>
          {isLoading ? "불러오는 중..." : "학습 시작"}
        </button>
      </div>

      {message ? <p className="message">{message}</p> : null}

      {currentItem && !isComplete ? (
        <div className="study-card">
          <div className="study-progress">
            {currentIndex + 1} / {items.length}
          </div>
          <div className="study-front">
            {currentItem.surface || currentItem.base_form}
          </div>
          {isAnswerVisible ? (
            <>
              <dl className="study-answer">
                <div>
                  <dt>읽기</dt>
                  <dd>{currentItem.reading || "-"}</dd>
                </div>
                <div>
                  <dt>뜻</dt>
                  <dd>{currentItem.meaning_ko || "-"}</dd>
                </div>
                <div>
                  <dt>품사</dt>
                  <dd>{currentItem.part_of_speech || "-"}</dd>
                </div>
                <div>
                  <dt>기본형</dt>
                  <dd>{currentItem.base_form}</dd>
                </div>
                <div className="answer-example">
                  <dt>예문</dt>
                  <dd>{currentItem.example_sentence || "-"}</dd>
                </div>
                {currentItem.context_explanation_ko ? (
                  <div className="answer-example">
                    <dt>AI 문맥 설명</dt>
                    <dd>{currentItem.context_explanation_ko}</dd>
                  </div>
                ) : null}
              </dl>
              <div className="study-actions">
                <button
                  type="button"
                  className="success-button"
                  onClick={() => onReview("correct")}
                  disabled={isReviewing}
                >
                  맞음
                </button>
                <button
                  type="button"
                  className="danger-button"
                  onClick={() => onReview("wrong")}
                  disabled={isReviewing}
                >
                  틀림
                </button>
              </div>
            </>
          ) : (
            <div className="study-actions">
              <button type="button" onClick={onShowAnswer}>
                정답 보기
              </button>
            </div>
          )}
        </div>
      ) : null}

      {isComplete ? (
        <div className="study-card complete-card">
          <h3>학습 완료</h3>
          <p>이번 세션 맞은 개수: {correctCount}</p>
          <p>이번 세션 틀린 개수: {wrongCount}</p>
          <p>오늘 복습을 완료했습니다.</p>
        </div>
      ) : null}
    </section>
  );
}
