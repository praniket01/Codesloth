import type { Metadata } from "next";
import "./globals.css";
export const metadata: Metadata = { title: "CodeSloth — Understand any codebase", description: "A local-first AI codebase explorer powered by open models." };
export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body>{children}</body></html>;
}
