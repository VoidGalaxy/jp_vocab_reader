"use client";

// ============================================================================
// Design Lab -- static, isolated design-review prototypes only.
//
// This route (/design-lab) is NOT linked from the app's nav/rail/bottom-tab
// anywhere -- reached only by typing the URL directly. It does not import
// anything from ../../components (the real screens), does not call any
// API, and holds no real user data -- every number/word/deck below is
// fixture data hard-coded in this file.
//
// This version compares 3 fully distinct visual directions (Desk Reader /
// Index Card Study / Quiet Library), each rendering the same 4 mini-screens
// (Home/Reader/Classify/StudyLog) so they can be judged side by side. The
// three directions differ in actual layout/component shape, not just color
// -- see design-lab.css's per-direction class blocks.
// ============================================================================

import "./design-lab.css";

function Shiori({
  size = 48,
  rotate = 0,
}: {
  size?: number;
  rotate?: number;
}) {
  return (
    <svg
      viewBox="0 0 64 88"
      width={size}
      height={(size * 88) / 64}
      className="shiori-character-svg"
      style={{ transform: `rotate(${rotate}deg)` }}
      aria-hidden="true"
    >
      <path
        className="shiori-character-body"
        d="M14 2 H50 A12 12 0 0 1 62 14 V84 L32 63 L2 84 V14 A12 12 0 0 1 14 2 Z"
      />
      <rect className="shiori-character-face" x="14" y="16" width="36" height="28" rx="10" />
      <circle className="shiori-character-eye" cx="26" cy="30" r="2.2" />
      <circle className="shiori-character-eye" cx="38" cy="30" r="2.2" />
      <path className="shiori-character-mouth" d="M26 36 Q32 41 38 36" />
      <line className="shiori-character-tassel" x1="32" y1="63" x2="32" y2="78" />
      <circle className="shiori-character-bead" cx="32" cy="81" r="3" />
    </svg>
  );
}

// ============================================================================
// Direction A -- Desk Reader
// ============================================================================
function DeskReaderDirection() {
  return (
    <section className="design-direction direction-desk-reader" aria-label="Direction A - Desk Reader">
      <div className="design-direction-header">
        <span className="design-direction-label">Direction A · Desk Reader</span>
        <h3 className="design-direction-title">책상 위에서 원문을 펼쳐 읽는 느낌</h3>
        <p className="design-direction-concept">
          따뜻한 나무 책상 표면, 종이/연필/포스트잇 같은 물리적 오브젝트, 책 페이지 가장자리에
          꽂힌 책갈피 시오리 -- 서재/독서 앱에 가장 가까운 방향.
        </p>
      </div>

      <div className="design-mini-grid">
        {/* Home */}
        <div className="design-mini-screen">
          <span className="design-mini-screen-label">Home</span>
          <div className="desk-reader-paper-sheet">
            <div className="desk-reader-bookmark-clip">
              <Shiori size={52} rotate={10} />
            </div>
            <h4 className="desk-reader-title">
              오늘 읽을 원문을
              <br />
              펼쳐볼까요?
            </h4>
            <p className="desk-reader-sub">모르는 단어를 눌러 노트에 담고, 짧게 복습하세요.</p>
            <div className="desk-reader-cta-row">
              <button type="button" className="desk-reader-cta-primary">
                원문 읽기 시작
              </button>
              <button type="button" className="desk-reader-cta-secondary">
                오늘 복습하기
              </button>
            </div>
            <div className="desk-reader-memo-stack">
              <div className="desk-reader-memo-line">闇 やみ · 어둠</div>
              <div className="desk-reader-memo-line">約束 やくそく · 약속</div>
              <div className="desk-reader-memo-line">剣 けん · 검</div>
            </div>
          </div>
        </div>

        {/* Reader */}
        <div className="design-mini-screen">
          <span className="design-mini-screen-label">Reader</span>
          <div className="desk-reader-paper-sheet">
            <p className="desk-reader-text">
              彼は<span className="desk-reader-word-selected">闇</span>の中で声を聞いた。
              少女は<span className="desk-reader-word-hi">約束</span>を思い出した。
              騎士は剣を握り、敵から王を守った。
            </p>
            <div className="desk-reader-note-card">
              <span className="desk-reader-note-surface">闇</span>
              <span className="desk-reader-note-reading">やみ</span>
              <div className="desk-reader-note-meaning">어둠</div>
              <p className="desk-reader-note-example">彼は闇の中で声を聞いた。</p>
              <button type="button" className="desk-reader-note-save">
                저장 바구니에 담기
              </button>
            </div>
          </div>
        </div>

        {/* Classify */}
        <div className="design-mini-screen">
          <span className="design-mini-screen-label">Classify</span>
          <div className="desk-reader-paper-sheet">
            <p className="desk-reader-sub" style={{ textAlign: "center" }}>
              단어 카드를 넘기며 분류해요
            </p>
            <div className="desk-reader-card-on-desk">
              <div className="desk-reader-pencil" />
              <div className="desk-reader-card-progress">7 / 28</div>
              <div className="desk-reader-card-surface">約束</div>
              <div className="desk-reader-card-reading">やくそく</div>
              <div className="desk-reader-card-meaning">약속</div>
              <div className="desk-reader-card-actions">
                <button type="button" style={{ background: "#4f8c66" }}>
                  아는 단어
                </button>
                <button type="button" style={{ background: "#dba054" }}>
                  헷갈리는 단어
                </button>
                <button type="button" style={{ background: "#d97a4a" }}>
                  모르는 단어
                </button>
                <button type="button" style={{ background: "#a89881" }}>
                  건너뛰기
                </button>
              </div>
            </div>
          </div>
        </div>

        {/* StudyLog */}
        <div className="design-mini-screen">
          <span className="design-mini-screen-label">StudyLog</span>
          <div className="desk-reader-paper-sheet desk-reader-journal-lines">
            <h4 className="desk-reader-title" style={{ fontSize: 16 }}>
              학습 기록장
            </h4>
            <div className="desk-reader-memo-stack">
              <div className="desk-reader-memo-line">오늘 복습 32개 · 최근 담은 단어 5개 · 어려운 단어 3개</div>
              <div className="desk-reader-memo-line">오늘 복습할 단어가 있어요.</div>
              <div className="desk-reader-memo-line">어려운 단어는 다시 나타나요.</div>
            </div>
            <div className="desk-reader-deck-row">
              <span style={{ fontSize: 11, fontWeight: 700 }}>기본 단어장 · 42%</span>
              <div className="desk-reader-deck-bar">
                <div className="desk-reader-deck-bar-fill" style={{ width: "42%" }} />
              </div>
            </div>
            <div className="desk-reader-deck-row">
              <span style={{ fontSize: 11, fontWeight: 700 }}>JLPT 추천 어휘 N3 · 18%</span>
              <div className="desk-reader-deck-bar">
                <div className="desk-reader-deck-bar-fill" style={{ width: "18%" }} />
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}

// ============================================================================
// Direction B -- Index Card Study
// ============================================================================
function IndexCardDirection() {
  return (
    <section className="design-direction direction-index-card" aria-label="Direction B - Index Card Study">
      <div className="design-direction-header">
        <span className="design-direction-label">Direction B · Index Card Study</span>
        <h3 className="design-direction-title">색인 카드함에서 단어를 모으고 넘기는 느낌</h3>
        <p className="design-direction-concept">
          카드 탭, 스택 카드 그림자, 상태별 컬러 라벨, compact drawer row -- 단어장/복습 앱에
          가장 가까운 방향.
        </p>
      </div>

      <div className="design-mini-grid">
        {/* Home */}
        <div className="design-mini-screen">
          <span className="design-mini-screen-label">Home</span>
          <div className="index-card-stack">
            <div className="index-card-main">
              <span className="index-card-tab">오늘의 카드함</span>
              <Shiori size={30} rotate={-6} />
              <h4 className="index-card-home-title">원문 읽기 시작</h4>
              <p className="index-card-home-sub">오늘 복습 카드 더미가 준비됐어요.</p>
              <button type="button" className="index-card-cta">
                읽기 시작
              </button>
              <div className="index-card-mini-row">
                <div className="index-card-mini">
                  闇
                  <strong>やみ</strong>
                </div>
                <div className="index-card-mini">
                  約束
                  <strong>やくそく</strong>
                </div>
                <div className="index-card-mini">
                  剣
                  <strong>けん</strong>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Reader */}
        <div className="design-mini-screen">
          <span className="design-mini-screen-label">Reader</span>
          <div className="index-card-stack">
            <div className="index-card-main">
              <span className="index-card-tab">원문</span>
              <div className="index-card-reader-layout" style={{ marginTop: 6 }}>
                <p className="index-card-reader-text">
                  彼は<span className="desk-reader-word-selected">闇</span>の中で声を聞いた。
                  少女は<span className="desk-reader-word-hi">約束</span>を思い出した。
                  騎士は剣を握った。
                </p>
                <div className="index-card-popout">
                  <div className="index-card-popout-surface">闇</div>
                  <div className="index-card-popout-reading">やみ</div>
                  <div className="index-card-popout-meaning">어둠</div>
                  <p style={{ margin: "4px 0 0", fontSize: 9 }}>彼は闇の中で声を聞いた。</p>
                  <button type="button" className="index-card-popout-save">
                    바구니에 담기
                  </button>
                </div>
              </div>
              <div className="index-card-drawer-slot">저장 바구니 · 2장 담김</div>
            </div>
          </div>
        </div>

        {/* Classify */}
        <div className="design-mini-screen">
          <span className="design-mini-screen-label">Classify</span>
          <div className="index-card-stack">
            <div className="index-card-main">
              <span className="index-card-tab">카드 분류</span>
              <div className="index-card-classify-progress">7 / 28</div>
              <div className="index-card-classify-surface">約束</div>
              <div className="index-card-classify-reading">やくそく</div>
              <div className="index-card-classify-meaning">약속</div>
              <div className="index-card-label-grid">
                <button type="button" style={{ background: "#4f8c66" }}>
                  아는 단어
                </button>
                <button type="button" style={{ background: "#dba054" }}>
                  헷갈리는 단어
                </button>
                <button type="button" style={{ background: "#d97a4a" }}>
                  모르는 단어
                </button>
                <button type="button" style={{ background: "#a89881" }}>
                  건너뛰기
                </button>
              </div>
              <div className="index-card-summary-row">
                <span className="index-card-summary-chip">완료 시 카드함 정리</span>
              </div>
            </div>
          </div>
        </div>

        {/* StudyLog */}
        <div className="design-mini-screen">
          <span className="design-mini-screen-label">StudyLog</span>
          <div className="index-card-stack">
            <div className="index-card-main">
              <span className="index-card-tab">학습 기록 카드함</span>
              <div className="index-card-mini-row" style={{ marginTop: 6 }}>
                <div className="index-card-mini">
                  오늘 복습
                  <strong>32개</strong>
                </div>
                <div className="index-card-mini">
                  최근 담음
                  <strong>5개</strong>
                </div>
                <div className="index-card-mini">
                  어려운 단어
                  <strong>3개</strong>
                </div>
              </div>
              <p style={{ fontSize: 10, color: "#6b5f3f", marginTop: 8 }}>
                최근 활동: 어려운 단어가 다시 나타나요.
              </p>
              <div className="index-card-drawer-row">
                <span className="index-card-drawer-row-tab" />
                <span className="index-card-drawer-row-body">
                  <strong>기본 단어장</strong>42% · 오늘 복습 12개
                </span>
              </div>
              <div className="index-card-drawer-row">
                <span className="index-card-drawer-row-tab" style={{ background: "#dba054" }} />
                <span className="index-card-drawer-row-body">
                  <strong>JLPT 추천 어휘 N3</strong>18% · 오늘 복습 6개
                </span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}

// ============================================================================
// Direction C -- Quiet Library
// ============================================================================
function QuietLibraryDirection() {
  return (
    <section className="design-direction direction-quiet-library" aria-label="Direction C - Quiet Library">
      <div className="design-direction-header">
        <span className="design-direction-label">Direction C · Quiet Library</span>
        <h3 className="design-direction-title">여백이 넓은 차분한 미니멀 독서 화면</h3>
        <p className="design-direction-concept">
          두꺼운 카드 테두리/그림자 대신 얇은 선과 넓은 여백, 큰 타이포그래피 -- 장식은 적지만
          책갈피/서가 느낌은 은은하게 유지되는 방향.
        </p>
      </div>

      <div className="design-mini-grid">
        {/* Home */}
        <div className="design-mini-screen" style={{ position: "relative" }}>
          <span className="design-mini-screen-label">Home</span>
          <div className="quiet-lib-shiori-mark">
            <Shiori size={34} />
          </div>
          <span className="quiet-lib-eyebrow">오늘의 서재</span>
          <h4 className="quiet-lib-title">
            오늘 읽을 원문을
            <br />
            펼쳐볼까요?
          </h4>
          <div className="quiet-lib-cta-row">
            <button type="button" className="quiet-lib-cta-primary">
              원문 읽기 시작
            </button>
            <button type="button" className="quiet-lib-cta-secondary">
              오늘 복습하기
            </button>
          </div>
          <hr className="quiet-lib-hairline" />
          <div className="quiet-lib-list">
            <div className="quiet-lib-list-row">
              <span>闇</span>
              <span>어둠</span>
            </div>
            <div className="quiet-lib-list-row">
              <span>約束</span>
              <span>약속</span>
            </div>
            <div className="quiet-lib-list-row">
              <span>剣</span>
              <span>검</span>
            </div>
          </div>
        </div>

        {/* Reader */}
        <div className="design-mini-screen">
          <span className="design-mini-screen-label">Reader</span>
          <span className="quiet-lib-eyebrow">원문</span>
          <p className="quiet-lib-reader-text" style={{ marginTop: 8 }}>
            彼は<span className="quiet-lib-word-mark">闇</span>の中で声を聞いた。
            少女は<span className="quiet-lib-word-soft">約束</span>を思い出した。
          </p>
          <div className="quiet-lib-note-column">
            <span className="quiet-lib-note-surface">闇</span>
            <span className="quiet-lib-note-reading">やみ</span>
            <div className="quiet-lib-note-meaning">어둠</div>
            <p className="quiet-lib-note-example">彼は闇の中で声を聞いた。</p>
            <button type="button" className="quiet-lib-note-save">
              저장 바구니에 담기
            </button>
          </div>
        </div>

        {/* Classify */}
        <div className="design-mini-screen">
          <span className="design-mini-screen-label">Classify</span>
          <span className="quiet-lib-eyebrow">빠른 분류</span>
          <div className="quiet-lib-flashcard">
            <div className="quiet-lib-flashcard-progress">7 / 28</div>
            <div className="quiet-lib-flashcard-surface">約束</div>
            <div className="quiet-lib-flashcard-reading">やくそく</div>
            <div className="quiet-lib-flashcard-meaning">약속</div>
            <div className="quiet-lib-flashcard-actions">
              <button type="button" className="quiet-lib-action-known">
                아는 단어
              </button>
              <button type="button" className="quiet-lib-action-uncertain">
                헷갈리는 단어
              </button>
              <button type="button" className="quiet-lib-action-unknown">
                모르는 단어
              </button>
              <button type="button" className="quiet-lib-action-skip">
                건너뛰기
              </button>
            </div>
          </div>
        </div>

        {/* StudyLog */}
        <div className="design-mini-screen">
          <span className="design-mini-screen-label">StudyLog</span>
          <span className="quiet-lib-eyebrow">학습 기록장</span>
          <h4 className="quiet-lib-title" style={{ fontSize: 19 }}>
            읽고 담고 복습한 흐름
          </h4>
          <p className="quiet-lib-journal-line">
            오늘 복습 32개, 최근 담은 단어 5개, 어려운 단어 3개가 있어요.
          </p>
          <p className="quiet-lib-journal-line">오늘 복습할 단어가 있어요.</p>
          <p className="quiet-lib-journal-line">어려운 단어는 다시 나타나요.</p>
          <hr className="quiet-lib-hairline" />
          <div className="quiet-lib-deck-row">
            <div className="quiet-lib-deck-row-head">
              <span>기본 단어장</span>
              <span>42%</span>
            </div>
            <div className="quiet-lib-deck-bar">
              <div className="quiet-lib-deck-bar-fill" style={{ width: "42%" }} />
            </div>
          </div>
          <div className="quiet-lib-deck-row">
            <div className="quiet-lib-deck-row-head">
              <span>JLPT 추천 어휘 N3</span>
              <span>18%</span>
            </div>
            <div className="quiet-lib-deck-bar">
              <div className="quiet-lib-deck-bar-fill" style={{ width: "18%" }} />
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}

export default function DesignLabPage() {
  return (
    <div className="design-lab">
      <p className="design-lab-banner">
        Design Lab -- 내부 디자인 검토용 정적 프로토타입 (실제 기능/라우트와
        무관, 운영 메뉴에 노출되지 않음) · 3개 방향 비교
      </p>
      <DeskReaderDirection />
      <IndexCardDirection />
      <QuietLibraryDirection />
    </div>
  );
}
