import type { Metadata } from "next";

import "./globals.css";

export const metadata: Metadata = {
  title: "ReliefLink ATLAS",
  description: "Human-governed disaster supply coordination",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
