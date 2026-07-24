"use client";

import { useEffect, useRef, type FormEvent } from "react";
import { classifyMessageTone } from "./coverageUtils";
import { ShieldIcon, UserIcon } from "./icons";

type CurrentUser = {
  id: number;
  email: string;
  display_name: string;
  auth_provider: string;
};

type AccountMenuProps = {
  user: CurrentUser | null;
  isOpen: boolean;
  onOpenChange: (open: boolean) => void;
  authMode: "login" | "register";
  email: string;
  password: string;
  displayName: string;
  message: string;
  isLoadingUser: boolean;
  isSubmitting: boolean;
  onAuthModeChange: (mode: "login" | "register") => void;
  onEmailChange: (value: string) => void;
  onPasswordChange: (value: string) => void;
  onDisplayNameChange: (value: string) => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
  onLogout: () => void;
};

// App Shell V2's top-right account entry point -- replaces the old
// full-width AccountPanel that used to repeat (login form or a logged-in
// summary card) above every single tab's content. Same login/register/
// logout wiring as before, just tucked behind one small trigger button
// instead of taking permanent real estate on every screen.
export function AccountMenu({
  user,
  isOpen,
  onOpenChange,
  authMode,
  email,
  password,
  displayName,
  message,
  isLoadingUser,
  isSubmitting,
  onAuthModeChange,
  onEmailChange,
  onPasswordChange,
  onDisplayNameChange,
  onSubmit,
  onLogout,
}: AccountMenuProps) {
  const isDevUser = !user || user.auth_provider === "dev";
  const messageTone = classifyMessageTone(message);
  const wrapRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!isOpen) {
      return;
    }
    function handlePointerDown(event: MouseEvent) {
      if (!wrapRef.current?.contains(event.target as Node)) {
        onOpenChange(false);
      }
    }
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        onOpenChange(false);
      }
    }
    document.addEventListener("mousedown", handlePointerDown);
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("mousedown", handlePointerDown);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [isOpen, onOpenChange]);

  const initial =
    !isDevUser && user ? user.display_name.trim().charAt(0).toUpperCase() : "";

  return (
    <div className="account-menu" ref={wrapRef}>
      <button
        type="button"
        className="account-menu-trigger"
        onClick={() => onOpenChange(!isOpen)}
        aria-haspopup="menu"
        aria-expanded={isOpen}
        aria-label={isDevUser ? "로그인" : `${user!.display_name} 계정 메뉴`}
      >
        <span className="account-menu-avatar" aria-hidden="true">
          {initial || <UserIcon className="account-menu-avatar-icon" />}
        </span>
        <span className="account-menu-trigger-label">
          {isDevUser ? "로그인" : user!.display_name}
        </span>
      </button>

      {isOpen ? (
        <div className="account-menu-panel" role="menu">
          {isDevUser ? (
            <form className="account-menu-form" onSubmit={onSubmit} noValidate>
              <h3 className="account-menu-title">
                {authMode === "login" ? "로그인" : "회원가입"}
              </h3>
              <p className="account-menu-hint">
                <ShieldIcon className="account-menu-hint-icon" />
                가입하면 단어장과 복습 기록이 계정에 저장돼요.
              </p>
              <label>
                이메일
                <input
                  type="email"
                  value={email}
                  onChange={(event) => onEmailChange(event.target.value)}
                  placeholder="test@example.com"
                  autoComplete="email"
                />
              </label>
              <label>
                비밀번호
                <input
                  type="password"
                  value={password}
                  onChange={(event) => onPasswordChange(event.target.value)}
                  placeholder="8자 이상"
                  autoComplete={
                    authMode === "login" ? "current-password" : "new-password"
                  }
                />
              </label>
              {authMode === "register" ? (
                <label>
                  표시 이름
                  <input
                    type="text"
                    value={displayName}
                    onChange={(event) => onDisplayNameChange(event.target.value)}
                    placeholder="비우면 이메일 앞부분"
                    autoComplete="nickname"
                  />
                </label>
              ) : null}
              <button
                type="submit"
                className="account-menu-submit"
                disabled={isSubmitting}
              >
                {isSubmitting
                  ? "처리 중"
                  : authMode === "login"
                    ? "로그인"
                    : "가입하고 시작하기"}
              </button>
              <button
                type="button"
                className="account-mode-switch"
                onClick={() =>
                  onAuthModeChange(authMode === "login" ? "register" : "login")
                }
              >
                {authMode === "login"
                  ? "계정이 없나요? 회원가입"
                  : "이미 계정이 있나요? 로그인"}
              </button>
              {message ? (
                <p className={`account-message message message--${messageTone}`}>
                  {message}
                </p>
              ) : null}
              {isLoadingUser ? (
                <p className="account-message">사용자 확인 중</p>
              ) : null}
            </form>
          ) : (
            <div className="account-menu-profile">
              <p className="account-menu-email">{user!.email}</p>
              <p className="account-menu-hint">
                저장한 단어와 복습 기록이 이 계정에 보관돼요.
              </p>
              {message ? (
                <p className={`account-message message message--${messageTone}`}>
                  {message}
                </p>
              ) : null}
              <button
                type="button"
                className="secondary-button compact-button account-menu-logout"
                onClick={onLogout}
              >
                로그아웃
              </button>
            </div>
          )}
        </div>
      ) : null}
    </div>
  );
}
