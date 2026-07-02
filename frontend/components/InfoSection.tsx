export function InfoSection() {
  return (
    <section className="tab-panel info-panel">
      <div>
        <h2>서비스 개요</h2>
        <p>
          이 앱은 일본어 원서와 웹소설 학습자를 위한 자동 단어장
          생성기입니다. 원문을 분석해 단어, 읽기, 품사, 뜻, 예문을 정리하고
          앱 안에서 바로 복습할 수 있게 합니다.
        </p>
      </div>

      <div>
        <h2>저장 정책</h2>
        <p>
          사용자가 붙여넣은 원문 전체는 DB에 저장하지 않습니다. 사용자가
          저장한 단어와 해당 단어가 나온 짧은 예문만 단어장 데이터로
          보관합니다.
        </p>
      </div>

      <div>
        <h2>현재 기능</h2>
        <ul>
          <li>일본어 원문 형태소 분석</li>
          <li>히라가나 읽기와 한국어 품사 표시</li>
          <li>기본 한국어 뜻과 예문 저장</li>
          <li>작품/책/챕터별 덱 관리</li>
          <li>단어장 조회, 상태 변경, 삭제</li>
          <li>CSV 다운로드</li>
          <li>플래시카드 학습 모드와 기본 복습 스케줄</li>
          <li>저장된 단어별 AI 문맥 설명 생성</li>
        </ul>
      </div>

      <div>
        <h2>TODO</h2>
        <ul>
          <li>사전 데이터 확장</li>
          <li>고급 간격 반복 기능</li>
          <li>Anki 전용 내보내기</li>
          <li>AI 문맥 설명 품질 개선</li>
        </ul>
      </div>
    </section>
  );
}
