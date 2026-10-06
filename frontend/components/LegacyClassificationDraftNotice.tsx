"use client";

// 이전 "빠른 분류" 탭의 기기 초안(classification-draft) 호환 경로 (Gate D).
// 초안이 있는 기기에서만 보이며, 사용자가 고를 때만 동작한다:
// - 원자료 내려받기: 저장값을 그대로 JSON 파일로. 서버로 보내지 않는다.
// - 원문을 읽기에서 열기: 원문만 읽기 탭 입력칸으로. 저장하지 않은 분류
//   판단은 옮기지 않고, 초안은 지우지 않는다(기존 읽기 작업 교체는 확인).
// - 초안 삭제: 확인 뒤 이 키 하나만 지운다.
// 자동 삭제·자동 이관·계정 귀속은 하지 않는다. 깨진 JSON이어도 내려받기와
// 삭제는 할 수 있다. 원문 전체를 화면에 보여 주지 않는다.
import { useEffect, useState } from "react";

type Props = {
  storageKey: string;
  /** 원문을 읽기 탭에 넣는다(기존 읽기 작업 교체 확인은 부모가). 취소하면 false. */
  onOpenInReading: (text: string) => boolean;
};

function readRaw(key: string): string | null {
  try {
    return window.localStorage.getItem(key);
  } catch {
    return null;
  }
}

function draftText(raw: string): string | null {
  try {
    const parsed = JSON.parse(raw) as { text?: unknown };
    return typeof parsed?.text === "string" && parsed.text.trim() ? parsed.text : null;
  } catch {
    return null;
  }
}

export function LegacyClassificationDraftNotice({ storageKey, onOpenInReading }: Props) {
  const [raw, setRaw] = useState<string | null>(null);
  const [message, setMessage] = useState("");

  useEffect(() => {
    setRaw(readRaw(storageKey));
  }, [storageKey]);

  if (raw === null) {
    return message ? (
      <p className="learning-plan-legacy" role="status">
        {message}
      </p>
    ) : null;
  }

  const text = draftText(raw);

  function download() {
    if (raw === null) return;
    const blob = new Blob([raw], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = "jp-vocab-reader-classification-draft.json";
    document.body.appendChild(link);
    link.click();
    link.remove();
    window.setTimeout(() => URL.revokeObjectURL(url), 0);
  }

  function remove() {
    if (!window.confirm("이 기기에 남은 이전 분류 초안을 지울까요? 지운 뒤에는 되돌릴 수 없어요.")) return;
    let removed = false;
    try {
      window.localStorage.removeItem(storageKey);
      // 실제로 지워졌는지 다시 확인한다(접근 거부 등으로 조용히 남을 수 있음).
      removed = window.localStorage.getItem(storageKey) === null;
    } catch {
      removed = false;
    }
    if (removed) {
      setRaw(null);
      setMessage("이전 분류 초안을 지웠어요.");
    } else {
      // 원자료는 그대로 두고 다시 시도할 수 있게 같은 줄에 알린다.
      setRaw(readRaw(storageKey) ?? raw);
      setMessage("초안을 지우지 못했어요. 원자료는 그대로예요. 다시 시도해 주세요.");
    }
  }

  return (
    <div className="learning-plan-legacy" role="region" aria-label="이전 분류 초안">
      <span>
        {text
          ? "이 기기에 이전 분류 초안이 남아 있어요."
          : "이 기기에 읽을 수 없는 이전 분류 초안이 남아 있어요."}
      </span>
      <button type="button" onClick={download}>
        원자료 내려받기
      </button>
      {text ? (
        <button type="button" onClick={() => onOpenInReading(text)}>
          원문을 읽기에서 열기
        </button>
      ) : null}
      <button type="button" onClick={remove}>
        {message ? "다시 삭제" : "초안 삭제"}
      </button>
      {message ? (
        <span className="learning-plan-legacy__error" role="alert">
          {message}
        </span>
      ) : null}
    </div>
  );
}
