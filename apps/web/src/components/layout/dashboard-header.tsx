"use client";

import { useAuthStore } from "@/stores/auth-store";
import { usePathname, useRouter } from "next/navigation";
import { LogOut, Building2, ChevronRight } from "lucide-react";
import { ThemeToggleInline } from "@/components/shared/theme-toggle";

/** Map route segments to human-readable breadcrumb labels. */
const BREADCRUMB_LABELS: Record<string, string> = {
  dashboard: "Home",
  contexts: "Contexts",
  chat: "Chat",
  admin: "Admin",
  sources: "Sources",
  databricks: "Databricks",
  confluence: "Confluence",
  "config-apis": "Config APIs",
  "context-engine": "Context Engine",
};

export function DashboardHeader() {
  const router = useRouter();
  const pathname = usePathname();
  const { user, orgName, orgId, logout } = useAuthStore();

  const handleSwitchOrg = () => {
    router.push("/org-picker");
  };

  const handleLogout = () => {
    logout();
    localStorage.removeItem("aira-auth");
    window.location.href = "/login";
  };

  // Build breadcrumbs from pathname
  const segments = pathname.split("/").filter(Boolean);
  const breadcrumbs = segments
    .map((seg) => BREADCRUMB_LABELS[seg] || null)
    .filter(Boolean) as string[];

  return (
    <header className="flex h-14 items-center justify-between border-b border-border bg-background px-6 pl-16 lg:pl-6 shadow-[0_1px_3px_0_rgb(0_0_0/0.04)]">
      <div className="flex items-center gap-4">
        {/* Org switcher */}
        <button
          onClick={handleSwitchOrg}
          aria-label={`Switch organization (current: ${orgName})`}
          className="flex items-center gap-2 rounded-lg border border-border px-3 py-1.5 text-sm transition-colors hover:bg-muted"
        >
          <Building2 className="h-3.5 w-3.5 text-muted-foreground" />
          <span className="font-semibold text-foreground">{orgName}</span>
          <span className="text-xs text-muted-foreground">#{orgId}</span>
        </button>

        {/* Breadcrumbs */}
        {breadcrumbs.length > 1 && (
          <nav aria-label="Breadcrumb" className="hidden items-center gap-1 md:flex">
            {breadcrumbs.map((label, i) => (
              <span key={i} className="flex items-center gap-1">
                {i > 0 && <ChevronRight className="h-3 w-3 text-muted-foreground/50" />}
                <span
                  className={
                    i === breadcrumbs.length - 1
                      ? "text-xs font-medium text-foreground"
                      : "text-xs text-muted-foreground"
                  }
                >
                  {label}
                </span>
              </span>
            ))}
          </nav>
        )}
      </div>

      <div className="flex items-center gap-3">
        <ThemeToggleInline />

        {/* User info */}
        <div className="hidden items-center gap-2 sm:flex">
          <div className="flex h-7 w-7 items-center justify-center rounded-full bg-primary/10 text-xs font-semibold text-primary uppercase">
            {user?.email?.[0] || "?"}
          </div>
          <span className="text-sm text-muted-foreground">{user?.email}</span>
        </div>

        {/* Sign out */}
        <button
          onClick={handleLogout}
          aria-label="Sign out"
          className="flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
        >
          <LogOut className="h-3.5 w-3.5" />
          <span className="hidden sm:inline">Sign out</span>
        </button>
      </div>
    </header>
  );
}
