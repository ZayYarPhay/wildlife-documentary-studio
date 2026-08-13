import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";

export const metadata: Metadata = {
  title: "Wildlife Documentary Studio",
  description: "Build source-backed wildlife documentaries, scene by scene.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>
        <header className="topbar">
          <Link href="/" className="brand"><span>W</span> Wildlife Studio</Link>
          <nav><Link href="/">Projects</Link><Link href="/settings">Settings</Link></nav>
        </header>
        <main>{children}</main>
      </body>
    </html>
  );
}

