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
  LayoutDashboard,
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

  return (
    <>
      {/* Mobile hamburger button — shown only on small screens */}
      <button
        onClick={() => setMobileOpen(true)}
        className="fixed left-4 top-4 z-40 rounded-lg border border-gray-200 bg-white p-2 shadow-sm lg:hidden"
        aria-label="Open navigation menu"
      >
        <Menu className="h-5 w-5 text-gray-600" />
      </button>

      {/* Backdrop for mobile */}
      {mobileOpen && (
        <div
          className="fixed inset-0 z-40 bg-black/30 lg:hidden"
          onClick={() => setMobileOpen(false)}
        />
      )}

      <aside
        className={cn(
          "flex w-60 flex-col border-r border-gray-200 bg-white",
          // Mobile: fixed overlay, hidden by default
          "fixed inset-y-0 left-0 z-50 transition-transform duration-200 lg:relative lg:translate-x-0",
          mobileOpen ? "translate-x-0" : "-translate-x-full",
        )}
      >
        {/* Mobile close button */}
        <button
          onClick={() => setMobileOpen(false)}
          className="absolute right-3 top-4 rounded-md p-1 text-gray-400 hover:text-gray-600 lg:hidden"
          aria-label="Close navigation menu"
        >
          <X className="h-4 w-4" />
        </button>
      <div className="flex h-14 items-center gap-2 border-b border-gray-200 px-4">
        <LayoutDashboard className="h-5 w-5 text-primary" />
        <span className="text-lg font-bold text-gray-900">aiRA</span>
        <span className="rounded bg-blue-100 px-1.5 py-0.5 text-[10px] font-medium text-blue-700">
          Context
        </span>
      </div>

      <nav className="flex-1 space-y-1 p-3" aria-label="Main navigation">
        <p className="mb-2 px-2 text-[11px] font-semibold uppercase tracking-wider text-gray-400">
          Modules
        </p>
        {navItems
          .filter((item) => {
            // Admin sees all modules
            if (user?.isAdmin) return true;
            const modules = user?.allowedModules;
            if (!modules) {
              // Modules not loaded yet — show only chat until /me/modules resolves
              return item.module === "general";
            }
            return modules.includes(item.module);
          })
          .map((item) => {
            const isActive = pathname.startsWith(item.href);
            return (
              <Link
                key={item.href}
                href={item.href}
                aria-current={isActive ? "page" : undefined}
                className={cn(
                  "flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm font-medium transition-colors",
                  isActive
                    ? "bg-primary/10 text-primary"
                    : "text-gray-600 hover:bg-gray-100 hover:text-gray-900"
                )}
              >
                <item.icon className="h-4 w-4" />
                {item.label}
              </Link>
            );
          })}

        {user?.isAdmin && (
          <>
            <div className="my-3 border-t border-gray-200" />
            <p className="mb-2 px-2 text-[11px] font-semibold uppercase tracking-wider text-gray-400">
              Administration
            </p>
            <Link
              href="/dashboard/admin"
              className={cn(
                "flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm font-medium transition-colors",
                pathname.startsWith("/dashboard/admin")
                  ? "bg-primary/10 text-primary"
                  : "text-gray-600 hover:bg-gray-100 hover:text-gray-900"
              )}
            >
              <Shield className="h-4 w-4" />
              Admin Panel
            </Link>
          </>
        )}
      </nav>
    </aside>
    </>
  );
}
