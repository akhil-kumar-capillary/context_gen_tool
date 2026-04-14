import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import { Providers } from "@/components/providers";
import { ThemeToggleFloating } from "@/components/shared/theme-toggle";
import { Toaster } from "sonner";

const inter = Inter({ subsets: ["latin"] });

export const metadata: Metadata = {
  title: "aiRA — Context Management Platform",
  description: "Intelligent context management for the aiRA AI platform. Powered by Capillary Pulse.",
  icons: {
    icon: "/favicon.ico",
    apple: "/apple-touch-icon.png",
  },
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body className={inter.className}>
        <Providers>
          {children}
          <ThemeToggleFloating />
          <Toaster position="bottom-right" richColors />
        </Providers>
      </body>
    </html>
  );
}
