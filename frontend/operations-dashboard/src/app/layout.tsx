import type { Metadata } from "next";
import { DashboardNavigation } from "@/components/DashboardNavigation";
import { isEvidenceBrowserEnabled } from "@/features/evidence/feature";
import "./globals.css";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "TraderNow Operations",
  description: "Internal read-only service status",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>
        <DashboardNavigation evidenceEnabled={isEvidenceBrowserEnabled()} />
        {children}
      </body>
    </html>
  );
}
