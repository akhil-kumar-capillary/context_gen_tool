"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useShallow } from "zustand/react/shallow";
import { useAuthStore } from "@/stores/auth-store";
import { AppSidebar } from "@/components/layout/app-sidebar";
import { DashboardHeader } from "@/components/layout/dashboard-header";
import { GlobalChatDrawer } from "@/components/chat/global-chat-drawer";
import { ErrorBoundary } from "@/components/error-boundary";

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const router = useRouter();
  const { isLoggedIn, orgId } = useAuthStore(
    useShallow((s) => ({ isLoggedIn: s.isLoggedIn, orgId: s.orgId })),
  );

  // Wait for Zustand persist hydration to avoid flash redirect on page refresh
  const [hydrated, setHydrated] = useState(false);
  useEffect(() => setHydrated(true), []);

  useEffect(() => {
    if (!hydrated) return;
    if (!isLoggedIn) {
      router.replace("/login");
    } else if (!orgId) {
      router.replace("/org-picker");
    }
  }, [hydrated, isLoggedIn, orgId, router]);

  if (!hydrated || !isLoggedIn || !orgId) {
    return null;
  }

  return (
    <div className="flex h-screen bg-gray-50">
      <AppSidebar />
      <div className="flex flex-1 flex-col overflow-hidden">
        <DashboardHeader />
        <div className="flex flex-1 overflow-hidden">
          <main className="flex-1 overflow-auto p-6">
            <ErrorBoundary>{children}</ErrorBoundary>
          </main>
          <GlobalChatDrawer />
        </div>
      </div>
    </div>
  );
}
