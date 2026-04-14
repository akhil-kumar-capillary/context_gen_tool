"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useShallow } from "zustand/react/shallow";
import { useAuthStore } from "@/stores/auth-store";
import { AppSidebar } from "@/components/layout/app-sidebar";
import { DashboardHeader } from "@/components/layout/dashboard-header";
import { GlobalChatDrawer } from "@/components/chat/global-chat-drawer";
import { ErrorBoundary } from "@/components/error-boundary";
import { CommandPalette } from "@/components/shared/command-palette";
import { SidebarSkeleton, Skeleton } from "@/components/ui/skeleton";
import { PageTransition } from "@/components/ui/page-transition";

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const router = useRouter();
  const { isLoggedIn, orgId } = useAuthStore(
    useShallow((s) => ({ isLoggedIn: s.isLoggedIn, orgId: s.orgId })),
  );

  // Wait for Zustand persist hydration to avoid flash redirect
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
    return (
      <div className="flex h-screen bg-muted/30">
        <div className="w-60 border-r border-border bg-background">
          <SidebarSkeleton />
        </div>
        <div className="flex flex-1 flex-col overflow-hidden">
          <div className="h-14 border-b border-border bg-background" />
          <main className="flex-1 p-6">
            <div className="space-y-4">
              <Skeleton className="h-7 w-48" />
              <Skeleton className="h-64 w-full rounded-lg" />
            </div>
          </main>
        </div>
      </div>
    );
  }

  return (
    <div className="flex h-screen bg-muted/30">
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:absolute focus:top-2 focus:left-2 focus:z-[100] focus:rounded-lg focus:bg-primary focus:px-4 focus:py-2 focus:text-primary-foreground focus:shadow-lg"
      >
        Skip to main content
      </a>
      <AppSidebar />
      <div className="flex flex-1 flex-col overflow-hidden">
        <DashboardHeader />
        <div className="flex flex-1 overflow-hidden">
          <main id="main-content" className="relative flex-1 overflow-y-auto px-4 pt-4 pb-24 lg:px-6 lg:pt-6 lg:pb-24" role="main">
            <ErrorBoundary>
              <PageTransition>{children}</PageTransition>
            </ErrorBoundary>
          </main>
          <GlobalChatDrawer />
        </div>
        <CommandPalette />
      </div>
    </div>
  );
}
