import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "TraderNow Operations",
  description: "Internal read-only service status",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
