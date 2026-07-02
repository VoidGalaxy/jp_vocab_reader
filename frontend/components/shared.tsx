"use client";

import type { TokenStatus } from "./types";

export const statusLabels: Record<TokenStatus, string> = {
  unclassified: "미분류",
  known: "아는 단어",
  unknown: "모르는 단어",
};

export function StatusSelect({
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

export function formatDateTime(value: string | null) {
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

export function formatNextReview(value: string | null) {
  if (!value) {
    return "다음 복습: 미정";
  }

  return `다음 복습: ${new Date(value).toLocaleDateString("ko-KR", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  })}`;
}
