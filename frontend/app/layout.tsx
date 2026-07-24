import type { Metadata } from "next";
import "./globals.css";

const SITE_TITLE = "책갈피 - 일본어 원문 읽기 단어장";
const SITE_DESCRIPTION =
  "일본어 웹소설과 원문을 읽으며 모르는 단어만 저장하고, 한국어 뜻과 함께 SRS로 복습하는 일본어 단어장 앱, 책갈피.";

export const metadata: Metadata = {
  title: SITE_TITLE,
  description: SITE_DESCRIPTION,
  openGraph: {
    title: SITE_TITLE,
    description: SITE_DESCRIPTION,
    locale: "ko_KR",
    type: "website",
  },
  twitter: {
    card: "summary",
    title: SITE_TITLE,
    description: SITE_DESCRIPTION,
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="ko">
      <body>{children}</body>
    </html>
  );
}
