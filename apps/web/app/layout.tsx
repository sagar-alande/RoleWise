import type { Metadata } from "next";
import { Inter } from "next/font/google";
import { AuthGate } from "@/components/AuthGate";
import { Nav } from "@/components/Nav";
import "./globals.css";

const inter = Inter({ subsets: ["latin"], variable: "--font-inter" });

export const metadata: Metadata = {
  title: "RoleWise",
  description: "Find jobs that fit, understand why, and close the gaps honestly.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className={`${inter.variable} min-h-screen font-sans antialiased`}>
        <AuthGate>
          <Nav />
          <main className="mx-auto max-w-5xl px-4 py-10">{children}</main>
        </AuthGate>
      </body>
    </html>
  );
}
