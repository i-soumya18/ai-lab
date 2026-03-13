import type { Metadata } from "next";
import "./globals.css";
import { Providers } from "./providers";

export const metadata: Metadata = {
  title: "AI Lab — Personal AI OS",
  description: "Fully local, privacy-first personal AI operating system",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="dark">
      <body className="bg-ailab-bg text-ailab-text antialiased h-screen overflow-hidden">
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
