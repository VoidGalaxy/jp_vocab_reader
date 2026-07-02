import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "JP Vocab Reader",
  description: "일본어 원문에서 학습 단어를 추출합니다.",
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
