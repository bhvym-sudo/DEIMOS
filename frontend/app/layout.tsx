import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "DEIMOS Intelligence Workspace",
  description: "Dark-web entity identification, mapping and OSINT workspace",
  icons: { icon: "/favicon.svg" },
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
