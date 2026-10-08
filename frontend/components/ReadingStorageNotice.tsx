"use client";

import {
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
  type KeyboardEvent,
  type ReactNode,
  type RefObject,
} from "react";

// 읽기 기기 저장의 최소 안내(읽기 저장 경계 Gate C·D·E).
// 계약: docs/plans/reading-storage-boundary/gate-b/CONTRACT.md.
// - 기본 화면에는 읽기 지면 바로 위에 한 줄 안내만 둔다(가장 중요한 상태 하나 +
//   남은 건수). 긴 설명과 복구 동작은 "자세히" 대화상자에서만 연다.
// - 한 줄 안내가 차지하는 높이는 --reading-notice-space로 내보내, 읽기 장면이
//   그만큼 뺀 가용 높이에 맞춰지게 한다(globals.css의 장면 계산이 같은 값을 쓴다).
// - 원문·단어 내용은 표시하지 않는다(존재·호환 여부·시각만).
// - 모든 쓰기·다운로드는 사용자가 버튼을 눌렀을 때만 부모 콜백으로 실행한다.

export type ReadingStorageStatus =
  | "ready"
  | "readOnly"
  | "conflict"
  | "unverified"
  | "corrupt"
  | "unavailable";

export type ReadingRecoveryOffer = {
  /** 옛 공통 키 자료: 호환(ok) / 읽을 수 없음(corrupt) / 없음(null). */
  legacy: "ok" | "corrupt" | null;
  legacyUpdatedAt: string | null;
  /** 방문자 영역에 이어 쓸 수 있는 자료가 있는지(로그인 계정에서만). */
  guest: boolean;
  guestUpdatedAt: string | null;
};

type Props = {
  ownerLabel: string;
  status: ReadingStorageStatus;
  /** unverified일 때 확인하지 못한 동작: 저장 또는 삭제. */
  unverifiedAction?: "save" | "remove";
  offer: ReadingRecoveryOffer | null;
  hasUnsavedRecovery: boolean;
  deckConfirm: { deckName: string } | null;
  busy: boolean;
  /** 덱 확인 요청 진행 중(다른 안내 버튼과 따로). */
  deckConfirmBusy?: boolean;
  message: string;
  /** 저장 실패 안내(원인·이전 저장본 유무를 담은 문장). 없으면 "". */
  saveWarning?: string;
  onCopy: (source: "legacy" | "guest", mode: "textOnly" | "full") => void;
  onDownloadLegacy: () => void;
  onDismissOffer: () => void;
  onDownloadCurrent: () => void;
  onLoadStored: () => void;
  onRecheck: () => void;
  onDownloadStoredRaw: () => void;
  onResetCorrupt: () => void;
  onRestoreRecovery: () => void;
  onDownloadRecovery: () => void;
  onDiscardRecovery: () => void;
  onConfirmDeck: () => void;
};

function formatWhen(iso: string | null): string {
  if (!iso) return "";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleString("ko-KR", { dateStyle: "medium", timeStyle: "short" });
}

export function ReadingStorageNotice(props: Props) {
  const {
    ownerLabel,
    status,
    offer,
    hasUnsavedRecovery,
    deckConfirm,
    busy,
    message,
  } = props;

  const saveWarning = props.saveWarning ?? "";
  const [isDetailsOpen, setIsDetailsOpen] = useState(false);
  const lineRef = useRef<HTMLElement>(null);
  const detailsButtonRef = useRef<HTMLButtonElement>(null);

  const blocks: JSX.Element[] = [];
  // 한 줄 안내 후보(우선순위 순). alert = 저장이 멈췄거나 실패한 중요한 상태.
  const summaries: Array<{ text: string; alert: boolean }> = [];

  if (saveWarning) {
    summaries.push({ text: "이 기기에 저장하지 못했어요", alert: true });
    blocks.push(
      <div key="save-failure" className="reading-storage-notice__block" role="alert">
        <p>{saveWarning}</p>
        <div className="reading-storage-notice__actions">
          <button type="button" onClick={props.onDownloadCurrent} disabled={busy}>
            이 창의 글 내려받기
          </button>
        </div>
      </div>,
    );
  }

  if (status === "conflict") {
    summaries.unshift({ text: "다른 창에서 바뀌어 자동 저장을 멈췄어요", alert: true });
    blocks.unshift(
      <div key="conflict" className="reading-storage-notice__block" role="alert">
        <p>
          다른 창에서 이 읽기 자료가 바뀌었어요. 덮어쓰지 않도록 이 창의 자동 저장을 멈췄어요.
        </p>
        <div className="reading-storage-notice__actions">
          <button type="button" onClick={props.onDownloadCurrent} disabled={busy}>
            이 창의 글 내려받기
          </button>
          <button type="button" onClick={props.onLoadStored} disabled={busy}>
            저장된 내용 불러오기
          </button>
        </div>
      </div>,
    );
  } else if (status === "unverified") {
    summaries.unshift({
      text:
        props.unverifiedAction === "remove"
          ? "지웠는지 확인하지 못했어요 · 자동 저장 멈춤"
          : "저장했는지 확인하지 못했어요 · 자동 저장 멈춤",
      alert: true,
    });
    blocks.unshift(
      <div key="unverified" className="reading-storage-notice__block" role="alert">
        <p>
          {props.unverifiedAction === "remove"
            ? "지웠는지 확인하지 못했어요. 지워졌을 수도, 남아 있을 수도 있어요. 확인할 때까지 자동 저장을 멈췄어요."
            : "저장했는지 확인하지 못했어요. 확인할 때까지 자동 저장을 멈췄어요."}
        </p>
        <div className="reading-storage-notice__actions">
          <button type="button" onClick={props.onRecheck} disabled={busy}>
            다시 확인
          </button>
          <button type="button" onClick={props.onDownloadCurrent} disabled={busy}>
            이 창의 글 내려받기
          </button>
        </div>
      </div>,
    );
  } else if (status === "readOnly") {
    summaries.push({ text: "이 브라우저에서는 자동 저장되지 않아요", alert: false });
    blocks.push(
      <div key="readonly" className="reading-storage-notice__block" role="status">
        <p>
          이 브라우저에서는 읽기 자료를 자동 저장할 수 없어요. 화면의 글은 창을 닫으면 사라지니 필요하면 내려받아 두세요.
        </p>
        <div className="reading-storage-notice__actions">
          <button type="button" onClick={props.onDownloadCurrent} disabled={busy}>
            글 내려받기
          </button>
        </div>
      </div>,
    );
  } else if (status === "corrupt") {
    summaries.unshift({ text: "저장된 읽기 자료를 읽을 수 없어요 · 자동 저장 멈춤", alert: true });
    blocks.unshift(
      <div key="corrupt" className="reading-storage-notice__block" role="alert">
        <p>
          이 기기에 저장된 읽기 자료를 읽을 수 없어 불러오지 않았어요. 원래 자료는 지우지 않았고, 자동 저장도 멈췄어요.
        </p>
        <div className="reading-storage-notice__actions">
          <button type="button" onClick={props.onDownloadStoredRaw} disabled={busy}>
            원자료 내려받기
          </button>
          <button type="button" onClick={props.onResetCorrupt} disabled={busy}>
            지우고 새로 시작
          </button>
        </div>
      </div>,
    );
  } else if (status === "unavailable") {
    summaries.unshift({ text: "브라우저 저장소를 열 수 없어요", alert: true });
    blocks.unshift(
      <div key="unavailable" className="reading-storage-notice__block" role="alert">
        <p>브라우저 저장소를 열 수 없어 읽기 자료를 불러오거나 저장하지 않아요.</p>
        <div className="reading-storage-notice__actions">
          <button type="button" onClick={props.onDownloadCurrent} disabled={busy}>
            글 내려받기
          </button>
        </div>
      </div>,
    );
  }

  if (hasUnsavedRecovery) {
    summaries.push({ text: "저장하지 못한 편집이 이 창에 있어요", alert: false });
    blocks.push(
      <div key="recovery" className="reading-storage-notice__block" role="status">
        <p>
          {ownerLabel}에서 저장하지 못한 편집이 이 창에 남아 있어요. 새로고침하거나 창을 닫으면 사라져요.
        </p>
        <div className="reading-storage-notice__actions">
          <button type="button" onClick={props.onRestoreRecovery} disabled={busy}>
            편집 되살리기
          </button>
          <button type="button" onClick={props.onDownloadRecovery} disabled={busy}>
            내려받기
          </button>
          <button type="button" onClick={props.onDiscardRecovery} disabled={busy}>
            버리기
          </button>
        </div>
      </div>,
    );
  }

  if (deckConfirm) {
    summaries.push({ text: "덱을 확인해야 단어를 저장할 수 있어요", alert: false });
    blocks.push(
      <div key="deck" className="reading-storage-notice__block" role="status">
        <p>
          가져온 분류는 아직 이 계정 단어장과 연결되지 않았어요. 읽기 덱을 확인하기 전에는 단어를 저장하지 않아요.
        </p>
        <div className="reading-storage-notice__actions">
          <button
            type="button"
            onClick={props.onConfirmDeck}
            disabled={busy || props.deckConfirmBusy || !deckConfirm.deckName}
          >
            {deckConfirm.deckName ? `‘${deckConfirm.deckName}’ 덱으로 확인` : "덱을 먼저 선택해 주세요"}
          </button>
        </div>
      </div>,
    );
  }

  if (offer && (offer.legacy || offer.guest) && status !== "readOnly" && status !== "unavailable") {
    // 복사할 원본: 호환되는 옛 공통 자료가 먼저, 없으면 방문자 자료.
    const source: "legacy" | "guest" | null =
      offer.legacy === "ok" ? "legacy" : offer.guest ? "guest" : null;
    const when = formatWhen(source === "guest" ? offer.guestUpdatedAt : offer.legacyUpdatedAt);
    summaries.push({
      text: source ? "이전 읽기 자료를 가져올 수 있어요" : "이전 읽기 자료를 읽을 수 없어요",
      alert: false,
    });
    blocks.push(
      <div key="offer" className="reading-storage-notice__block" role="status">
        <p>
          {source === "legacy"
            ? "이 기기에 계정 구분 전에 저장된 읽기 자료가 있어요"
            : source === "guest"
              ? "방문자로 읽던 자료가 이 기기에 있어요"
              : "이 기기에 계정 구분 전에 저장된 읽기 자료가 있지만, 읽을 수 없는 형식이라 가져올 수 없어요"}
          {when ? ` (${when})` : ""}.{" "}
          {source
            ? `본인 자료라면 ${ownerLabel}의 빈 읽기 영역으로 복사할 수 있어요. 원래 자료는 지우지 않아요.`
            : "원래 자료는 그대로 두었어요."}
        </p>
        <div className="reading-storage-notice__actions">
          {source ? (
            <>
              <button
                type="button"
                className="is-primary"
                onClick={() => props.onCopy(source, "textOnly")}
                disabled={busy}
              >
                원문만 가져오기
              </button>
              <button type="button" onClick={() => props.onCopy(source, "full")} disabled={busy}>
                분류까지 모두 가져오기
              </button>
            </>
          ) : null}
          {offer.legacy ? (
            <button type="button" onClick={props.onDownloadLegacy} disabled={busy}>
              이전 자료 원본 내려받기
            </button>
          ) : null}
          <button type="button" onClick={props.onDismissOffer} disabled={busy}>
            닫기
          </button>
        </div>
      </div>,
    );
  }

  const hasNotice = blocks.length > 0 || Boolean(message);
  useReadingNoticeSpace(lineRef, hasNotice);

  // 상세에서 더는 보여 줄 내용이 없으면 닫는다.
  useEffect(() => {
    if (blocks.length === 0 && isDetailsOpen) setIsDetailsOpen(false);
  }, [blocks.length, isDetailsOpen]);

  if (!hasNotice) return null;

  const top = summaries[0];
  const lineText = top ? top.text : message;
  const extra = summaries.length > 1 ? ` 외 ${summaries.length - 1}건` : "";
  const isAlert = Boolean(top?.alert);

  return (
    <>
      <aside
        ref={lineRef}
        className={`reading-storage-line${isAlert ? " is-alert" : ""}`}
        aria-label="읽기 자료 저장 안내"
      >
        <p
          className="reading-storage-line__text"
          role={isAlert ? "alert" : "status"}
          title={lineText + extra}
        >
          {lineText}
          {extra ? <span className="reading-storage-line__extra">{extra}</span> : null}
        </p>
        {blocks.length > 0 ? (
          <button
            type="button"
            ref={detailsButtonRef}
            className="reading-storage-line__details"
            aria-haspopup="dialog"
            aria-expanded={isDetailsOpen}
            onClick={() => setIsDetailsOpen(true)}
          >
            자세히
          </button>
        ) : null}
      </aside>
      {isDetailsOpen ? (
        <ReadingDialogFrame
          titleId="reading-storage-details-title"
          className="reading-storage-details"
          onClose={() => setIsDetailsOpen(false)}
          returnFocusRef={detailsButtonRef}
        >
          <div className="reading-storage-details__head">
            <h2 id="reading-storage-details-title">읽기 자료 저장 안내</h2>
            <button type="button" onClick={() => setIsDetailsOpen(false)}>
              닫기
            </button>
          </div>
          {blocks}
          {message ? (
            <p className="reading-storage-notice__message" role="status">
              {message}
            </p>
          ) : null}
        </ReadingDialogFrame>
      ) : null}
    </>
  );
}

/** 한 줄 안내가 보이는 동안 그 높이(바깥 여백 포함)를 --reading-notice-space로 내보낸다. */
function useReadingNoticeSpace(ref: RefObject<HTMLElement>, visible: boolean) {
  useLayoutEffect(() => {
    const root = document.documentElement;
    const element = ref.current;
    if (!visible || !element) {
      root.style.setProperty("--reading-notice-space", "0px");
      return;
    }
    const update = () => {
      const style = getComputedStyle(element);
      const space =
        element.offsetHeight +
        parseFloat(style.marginTop || "0") +
        parseFloat(style.marginBottom || "0");
      root.style.setProperty("--reading-notice-space", `${Math.ceil(space)}px`);
    };
    update();
    const observer = typeof ResizeObserver !== "undefined" ? new ResizeObserver(update) : null;
    observer?.observe(element);
    // 여백은 화면 폭 구간마다 달라지므로(태블릿·폰) 창 크기 변화에도 다시 잰다.
    window.addEventListener("resize", update);
    return () => {
      observer?.disconnect();
      window.removeEventListener("resize", update);
      root.style.setProperty("--reading-notice-space", "0px");
    };
  }, [ref, visible]);
}

/**
 * 접근 가능한 대화상자 틀: 열릴 때 첫 단추(또는 initialFocusRef)에 포커스, Tab은
 * 안에서만 돌고, Escape는 onClose, 닫히면 returnFocusRef → 연 요소 → 계정 메뉴 단추
 * 순으로 남아 있는 곳에 포커스를 돌린다.
 */
function ReadingDialogFrame({
  titleId,
  describedById,
  className,
  onClose,
  returnFocusRef,
  initialFocusRef,
  children,
}: {
  titleId: string;
  describedById?: string;
  className: string;
  onClose: () => void;
  returnFocusRef?: RefObject<HTMLElement>;
  initialFocusRef?: RefObject<HTMLElement>;
  children: ReactNode;
}) {
  const cardRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const previous = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const returnTarget = returnFocusRef?.current ?? null;
    const first =
      initialFocusRef?.current ??
      cardRef.current?.querySelector<HTMLElement>("button:not([disabled])") ??
      cardRef.current;
    first?.focus();
    return () => {
      const target =
        returnTarget && returnTarget.isConnected
          ? returnTarget
          : previous && previous.isConnected
            ? previous
            : document.querySelector<HTMLElement>('[aria-label$="계정 메뉴"]') ??
              document.querySelector<HTMLElement>("header button");
      target?.focus();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function handleKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    if (event.key === "Escape") {
      event.preventDefault();
      onClose();
      return;
    }
    if (event.key !== "Tab") return;
    const focusable = Array.from(
      cardRef.current?.querySelectorAll<HTMLElement>("button:not([disabled])") ?? [],
    );
    if (focusable.length === 0) return;
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    const active = document.activeElement;
    if (event.shiftKey && (active === first || !cardRef.current?.contains(active))) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && (active === last || !cardRef.current?.contains(active))) {
      event.preventDefault();
      first.focus();
    }
  }

  return (
    <div
      className="reading-switch-dialog"
      role="dialog"
      aria-modal="true"
      aria-labelledby={titleId}
      aria-describedby={describedById}
      onKeyDown={handleKeyDown}
    >
      <div className={`reading-switch-dialog__card ${className}`.trim()} ref={cardRef} tabIndex={-1}>
        {children}
      </div>
    </div>
  );
}

/** 계정 확인 전·실패 중 읽기 지면 대신 보여 주는 자리. 복원·저장을 하지 않는다. */
export function ReadingAccountGate({
  failed,
  onRetry,
}: {
  failed: boolean;
  onRetry: () => void;
}) {
  return (
    <section className="reading-account-gate" aria-live="polite">
      {failed ? (
        <>
          <p>계정을 확인하지 못해 읽기 자료를 열지 않았어요.</p>
          <button type="button" onClick={onRetry}>
            다시 확인
          </button>
        </>
      ) : (
        <p>계정을 확인하고 있어요…</p>
      )}
    </section>
  );
}

/** 미저장 편집이 있을 때 수동 계정 전환 확인. 내려받기는 전환 승인이 아니다. */
export function ReadingSwitchDialog({
  reason,
  onStay,
  onDownload,
  onContinue,
}: {
  reason: string;
  onStay: () => void;
  onDownload: () => void;
  onContinue: () => void;
}) {
  const stayRef = useRef<HTMLButtonElement>(null);
  return (
    <ReadingDialogFrame
      titleId="reading-switch-title"
      describedById="reading-switch-reason"
      className=""
      onClose={onStay}
      initialFocusRef={stayRef}
    >
      <h2 id="reading-switch-title">저장하지 못한 읽기 편집이 있어요</h2>
      <p id="reading-switch-reason">{reason}</p>
      <p>
        계속하면 이 창에서만 잠시 보관해요. 같은 계정으로 다시 들어오면 되살릴 수 있지만, 새로고침하거나 창을 닫으면 사라져요.
      </p>
      <div className="reading-switch-dialog__actions">
        <button type="button" className="is-primary" onClick={onStay} ref={stayRef}>
          머무르기
        </button>
        <button type="button" onClick={onDownload}>
          글 내려받기
        </button>
        <button type="button" onClick={onContinue}>
          그래도 계속
        </button>
      </div>
    </ReadingDialogFrame>
  );
}
