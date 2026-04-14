"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";
import { useAuthStore } from "@/stores/auth-store";
import {
  FileText,
  Database,
  BookOpen,
  Settings2,
  Shield,
  MessageSquare,
  GitBranch,
  Menu,
  X,
} from "lucide-react";
import { useState, useEffect } from "react";

const navItems = [
  {
    label: "Chat",
    href: "/dashboard/chat",
    icon: MessageSquare,
    module: "general",
  },
  {
    label: "Contexts",
    href: "/dashboard/contexts",
    icon: FileText,
    module: "context_management",
  },
  {
    label: "Databricks",
    href: "/dashboard/sources/databricks",
    icon: Database,
    module: "databricks",
  },
  {
    label: "Confluence",
    href: "/dashboard/sources/confluence",
    icon: BookOpen,
    module: "confluence",
  },
  {
    label: "Config APIs",
    href: "/dashboard/sources/config-apis",
    icon: Settings2,
    module: "config_apis",
  },
  {
    label: "Context Engine",
    href: "/dashboard/context-engine",
    icon: GitBranch,
    module: "context_engine",
  },
];

export function AppSidebar() {
  const pathname = usePathname();
  const { user } = useAuthStore();
  const [mobileOpen, setMobileOpen] = useState(false);

  // Close mobile menu on navigation
  useEffect(() => {
    setMobileOpen(false);
  }, [pathname]);

  const renderNavItem = (item: (typeof navItems)[0]) => {
    const isActive = pathname.startsWith(item.href);
    return (
      <Link
        key={item.href}
        href={item.href}
        aria-current={isActive ? "page" : undefined}
        title={item.label}
        className={cn(
          "group flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm font-medium transition-all",
          isActive
            ? "bg-primary/10 text-primary border-l-2 border-primary -ml-px"
            : "text-muted-foreground hover:bg-muted hover:text-foreground",
        )}
      >
        <item.icon className={cn("h-4 w-4 shrink-0", isActive && "text-primary")} />
        <span className="truncate">{item.label}</span>
      </Link>
    );
  };

  const filteredItems = navItems.filter((item) => {
    if (user?.isAdmin) return true;
    const modules = user?.allowedModules;
    if (!modules) return item.module === "general";
    return modules.includes(item.module);
  });

  return (
    <>
      {/* Mobile hamburger */}
      <button
        onClick={() => setMobileOpen(true)}
        className="fixed left-4 top-4 z-40 rounded-lg border border-border bg-background p-2 shadow-sm lg:hidden"
        aria-label="Open navigation menu"
      >
        <Menu className="h-5 w-5 text-muted-foreground" />
      </button>

      {/* Mobile backdrop */}
      {mobileOpen && (
        <div
          className="fixed inset-0 z-40 bg-black/30 backdrop-blur-sm lg:hidden"
          onClick={() => setMobileOpen(false)}
        />
      )}

      <aside
        className={cn(
          "flex w-60 flex-col border-r border-border bg-background",
          "fixed inset-y-0 left-0 z-50 transition-transform duration-200 ease-out lg:relative lg:translate-x-0",
          mobileOpen ? "translate-x-0" : "-translate-x-full",
        )}
      >
        {/* Mobile close */}
        <button
          onClick={() => setMobileOpen(false)}
          className="absolute right-3 top-4 rounded-md p-1 text-muted-foreground hover:text-foreground lg:hidden"
          aria-label="Close navigation menu"
        >
          <X className="h-4 w-4" />
        </button>

        {/* Logo */}
        <div className="flex h-14 items-center gap-2.5 border-b border-border px-4">
          <span className="text-base font-bold text-foreground tracking-tight">aiRA</span>
          <span className="text-xs text-muted-foreground">Context Platform</span>
        </div>

        {/* Navigation */}
        <nav className="flex-1 space-y-1 px-3 py-4" aria-label="Main navigation">
          <p className="mb-2 px-3 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
            Modules
          </p>
          {filteredItems.map(renderNavItem)}

          {user?.isAdmin && (
            <>
              <div className="my-3 border-t border-border" />
              <p className="mb-2 px-3 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                Administration
              </p>
              {renderNavItem({
                label: "Admin Panel",
                href: "/dashboard/admin",
                icon: Shield,
                module: "admin",
              })}
            </>
          )}
        </nav>

        {/* Footer — user info */}
        <div className="border-t border-border px-4 py-3">
          <div className="flex items-center gap-2.5">
            <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-muted text-xs font-semibold text-muted-foreground uppercase">
              {user?.email?.[0] || "?"}
            </div>
            <div className="min-w-0">
              <p className="truncate text-xs font-medium text-foreground">
                {user?.displayName || user?.email}
              </p>
              <p className="truncate text-xs text-muted-foreground">
                {user?.isAdmin ? "Admin" : "Member"}
              </p>
            </div>
          </div>
        </div>
      </aside>
    </>
  );
}
