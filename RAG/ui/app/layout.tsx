import type { Metadata } from "next";
import "./globals.css";
import { CopilotKit } from "@copilotkit/react-core";

export const metadata: Metadata = {
  title: "arXiv Research Assistant",
  description: "AI-powered arXiv paper search and Q&A using CopilotKit",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>
        <CopilotKit runtimeUrl="/api/copilotkit">
          {children}
        </CopilotKit>
      </body>
    </html>
  );
}
