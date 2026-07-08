"use client";

import type { PriorityVocabEntry, TokenStatus } from "./types";
import { StatusSelect, statusLabels } from "./shared";

type PriorityVocabListProps = {
  items: PriorityVocabEntry[];
  onStatusChange: (index: number, status: TokenStatus) => void;
};

export function PriorityVocabList({ items, onStatusChange }: PriorityVocabListProps) {
  if (items.length === 0) {
    return null;
  }

  return (
    <div className="priority-vocab-list">
      <h3 className="priority-vocab-title">이 텍스트에서 먼저 볼 단어</h3>
      <ul className="priority-vocab-items">
        {items.map((item) => (
          <li
            key={`${item.base_form}-${item.reading}-${item.tokenIndex}`}
            className={`priority-vocab-item priority-vocab-item-${item.status}`}
          >
            <div className="priority-vocab-main">
              <span className="priority-vocab-word">
                {item.surface || item.base_form}
              </span>
              {item.reading ? (
                <span className="priority-vocab-reading">{item.reading}</span>
              ) : null}
              <span className="priority-vocab-status-badge">
                {statusLabels[item.status]}
              </span>
              <span className="priority-vocab-occurrence">
                {item.occurrence_count}회 등장
              </span>
            </div>
            <div className="priority-vocab-meaning">
              {item.meaning_ko || "뜻 후보 없음"}
            </div>
            <div className="priority-vocab-actions">
              <StatusSelect
                value={item.status}
                label={`${item.surface || item.base_form} 상태`}
                onChange={(status) => onStatusChange(item.tokenIndex, status)}
              />
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}
