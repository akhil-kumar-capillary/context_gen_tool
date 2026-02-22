"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuthStore } from "@/stores/auth-store";
import { AppSidebar } from "@/components/layout/app-sidebar";
import { DashboardHeader } from "@/components/layout/dashboard-header";

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const router = useRouter();
  const { isLoggedIn, orgId } = useAuthStore();

  useEffect(() => {
    if (!isLoggedIn) {
      router.replace("/login");
    } else if (!orgId) {
      router.replace("/org-picker");
    }
  }, [isLoggedIn, orgId, router]);

  if (!isLoggedIn || !orgId) {
    return null;
  }

  return (
    <div className="flex h-screen bg-gray-50">
      <AppSidebar />
      <div className="flex flex-1 flex-col overflow-hidden">
        <DashboardHeader />
        <main className="flex-1 overflow-auto p-6">{children}</main>
      </div>
    </div>
  );
}
