import type { Metadata } from "next";

import "./globals.css";

export const metadata: Metadata = {
  title: "OPSEC Mirror",
  description: "Defensive OSINT mirror for exposure analysis."
};


export default function RootLayout({
  children
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
