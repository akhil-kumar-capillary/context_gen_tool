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
} from "lucide-react";

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
];

export function AppSidebar() {
  const pathname = usePathname();
  const { user } = useAuthStore();

  return (
    <aside className="flex w-60 flex-col border-r border-gray-200 bg-white">
      <div className="flex h-14 items-center gap-2 border-b border-gray-200 px-4">
        <LayoutDashboard className="h-5 w-5 text-primary" />
        <span className="text-lg font-bold text-gray-900">aiRA</span>
        <span className="rounded bg-blue-100 px-1.5 py-0.5 text-[10px] font-medium text-blue-700">
          Context
        </span>
      </div>

      <nav className="flex-1 space-y-1 p-3">
        <p className="mb-2 px-2 text-[11px] font-semibold uppercase tracking-wider text-gray-400">
          Modules
        </p>
        {navItems.map((item) => {
          const isActive = pathname.startsWith(item.href);
          return (
            <Link
              key={item.href}
              href={item.href}
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
  );
}
