"use client";

import type { TokenStatus, TokenWithStatus } from "./types";
import { statusLabels } from "./shared";

type TokenDetailSheetProps = {
  token: TokenWithStatus;
  onClose: () => void;
  onStatusChange: (status: TokenStatus) => void;
};

export function TokenDetailSheet({
  token,
  onClose,
  onStatusChange,
}: TokenDetailSheetProps) {
  const label = token.surface || token.base_form;

  return (
    <div className="token-sheet-overlay" role="presentation" onClick={onClose}>
      <div
        className="token-sheet"
        role="dialog"
        aria-modal="true"
        aria-label={`${label} 단어 정보`}
        onClick={(event) => event.stopPropagation()}
      >
        <div className="token-sheet-header">
          <span className="token-sheet-word">{label}</span>
          <button
            type="button"
            className="secondary-button token-sheet-close"
            onClick={onClose}
          >
            닫기
          </button>
        </div>
        <dl className="classify-details">
          <div>
            <dt>기본형</dt>
            <dd>{token.base_form || "-"}</dd>
          </div>
          <div>
            <dt>읽기</dt>
            <dd>{token.reading || "-"}</dd>
          </div>
          <div>
            <dt>품사</dt>
            <dd>{token.part_of_speech || "-"}</dd>
          </div>
          <div>
            <dt>한국어 뜻</dt>
            <dd>{token.meaning_ko || "뜻 후보 없음"}</dd>
          </div>
          <div>
            <dt>JLPT 추천 레벨</dt>
            <dd>
              {token.jlpt_level ? (
                <>
                  {token.jlpt_level}
                  <span className="jlpt-detail-hint">
                    {" "}
                    · JLPT 추천 어휘 기준이며, 공식 JLPT 어휘 목록은
                    아닙니다.
                  </span>
                </>
              ) : (
                "-"
              )}
            </dd>
          </div>
        </dl>
        <p className="token-sheet-status">
          현재 상태: <strong>{statusLabels[token.status]}</strong>
        </p>
        <div className="classify-actions">
          <button
            type="button"
            className="success-button"
            onClick={() => onStatusChange("known")}
          >
            {statusLabels.known}
          </button>
          <button
            type="button"
            className="warning-button"
            onClick={() => onStatusChange("uncertain")}
          >
            {statusLabels.uncertain}
          </button>
          <button
            type="button"
            className="danger-button"
            onClick={() => onStatusChange("unknown")}
          >
            {statusLabels.unknown}
          </button>
          <button
            type="button"
            className="secondary-button"
            onClick={() => onStatusChange("unclassified")}
          >
            미분류 / 건너뛰기
          </button>
        </div>
      </div>
    </div>
  );
}
