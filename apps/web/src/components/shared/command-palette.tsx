"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Command } from "cmdk";
import {
  MessageSquare,
  FileText,
  Database,
  BookOpen,
  Settings2,
  GitBranch,
  Shield,
  Plus,
  Sparkles,
  Search,
} from "lucide-react";
import { useAuthStore } from "@/stores/auth-store";
import { useContextStore } from "@/stores/context-store";
import { useChatStore } from "@/stores/chat-store";

interface CommandItem {
  id: string;
  label: string;
  icon: React.ReactNode;
  group: "navigation" | "actions";
  module?: string;
  action: () => void;
  keywords?: string;
}

export function CommandPalette() {
  const [open, setOpen] = useState(false);
  const router = useRouter();
  const { user } = useAuthStore();

  // Global keyboard shortcut
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        setOpen((prev) => !prev);
      }
    };
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, []);

  const navigate = (path: string) => {
    router.push(path);
    setOpen(false);
  };

  const items: CommandItem[] = [
    // Navigation
    {
      id: "nav-chat",
      label: "Chat",
      icon: <MessageSquare className="h-4 w-4" />,
      group: "navigation",
      module: "general",
      action: () => navigate("/dashboard/chat"),
      keywords: "chat message ai assistant",
    },
    {
      id: "nav-contexts",
      label: "Contexts",
      icon: <FileText className="h-4 w-4" />,
      group: "navigation",
      module: "context_management",
      action: () => navigate("/dashboard/contexts"),
      keywords: "context documents manage",
    },
    {
      id: "nav-databricks",
      label: "Databricks",
      icon: <Database className="h-4 w-4" />,
      group: "navigation",
      module: "databricks",
      action: () => navigate("/dashboard/sources/databricks"),
      keywords: "databricks sql notebooks extract",
    },
    {
      id: "nav-confluence",
      label: "Confluence",
      icon: <BookOpen className="h-4 w-4" />,
      group: "navigation",
      module: "confluence",
      action: () => navigate("/dashboard/sources/confluence"),
      keywords: "confluence wiki pages",
    },
    {
      id: "nav-config-apis",
      label: "Config APIs",
      icon: <Settings2 className="h-4 w-4" />,
      group: "navigation",
      module: "config_apis",
      action: () => navigate("/dashboard/sources/config-apis"),
      keywords: "config api loyalty campaigns",
    },
    {
      id: "nav-context-engine",
      label: "Context Engine",
      icon: <GitBranch className="h-4 w-4" />,
      group: "navigation",
      module: "context_engine",
      action: () => navigate("/dashboard/context-engine"),
      keywords: "context engine tree generate",
    },
    ...(user?.isAdmin
      ? [
          {
            id: "nav-admin",
            label: "Admin Panel",
            icon: <Shield className="h-4 w-4" />,
            group: "navigation" as const,
            action: () => navigate("/dashboard/admin"),
            keywords: "admin users roles permissions",
          },
        ]
      : []),
    // Actions
    {
      id: "action-new-context",
      label: "New Context",
      icon: <Plus className="h-4 w-4" />,
      group: "actions",
      module: "context_management",
      action: () => {
        navigate("/dashboard/contexts");
        setTimeout(() => useContextStore.getState().setIsCreating(true), 100);
      },
      keywords: "create new context document",
    },
    {
      id: "action-new-chat",
      label: "New Conversation",
      icon: <MessageSquare className="h-4 w-4" />,
      group: "actions",
      module: "general",
      action: () => {
        useChatStore.getState().newConversation();
        navigate("/dashboard/chat");
      },
      keywords: "new chat conversation",
    },
    {
      id: "action-generate-tree",
      label: "Generate Context Tree",
      icon: <Sparkles className="h-4 w-4" />,
      group: "actions",
      module: "context_engine",
      action: () => navigate("/dashboard/context-engine"),
      keywords: "generate tree build organize",
    },
  ];

  // Filter by module access
  const accessibleItems = items.filter((item) => {
    if (!item.module) return true;
    if (user?.isAdmin) return true;
    return user?.allowedModules?.includes(item.module);
  });

  const navItems = accessibleItems.filter((i) => i.group === "navigation");
  const actionItems = accessibleItems.filter((i) => i.group === "actions");

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-[80]">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/40 backdrop-blur-sm"
        onClick={() => setOpen(false)}
      />

      {/* Dialog */}
      <div className="absolute top-[20%] left-1/2 -translate-x-1/2 w-full max-w-lg">
        <Command
          className="rounded-xl bg-background shadow-2xl border border-border overflow-hidden"
          onKeyDown={(e) => {
            if (e.key === "Escape") setOpen(false);
          }}
        >
          {/* Input */}
          <div className="flex items-center gap-2 border-b border-border px-4 h-12">
            <Search className="h-4 w-4 text-muted-foreground shrink-0" />
            <Command.Input
              placeholder="Search pages and actions..."
              className="flex-1 bg-transparent text-sm text-foreground placeholder:text-muted-foreground outline-none"
              autoFocus
            />
            <kbd className="hidden sm:inline-flex h-5 items-center gap-1 rounded border border-border bg-muted px-1.5 text-xs font-mono text-muted-foreground">
              ESC
            </kbd>
          </div>

          {/* Results */}
          <Command.List className="max-h-72 overflow-y-auto p-2">
            <Command.Empty className="py-6 text-center text-sm text-muted-foreground">
              No results found.
            </Command.Empty>

            {navItems.length > 0 && (
              <Command.Group
                heading="Navigation"
                className="[&_[cmdk-group-heading]]:px-2 [&_[cmdk-group-heading]]:py-1.5 [&_[cmdk-group-heading]]:text-xs [&_[cmdk-group-heading]]:font-semibold [&_[cmdk-group-heading]]:text-muted-foreground [&_[cmdk-group-heading]]:uppercase [&_[cmdk-group-heading]]:tracking-wider"
              >
                {navItems.map((item) => (
                  <Command.Item
                    key={item.id}
                    value={`${item.label} ${item.keywords || ""}`}
                    onSelect={() => {
                      item.action();
                      setOpen(false);
                    }}
                    className="flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm text-muted-foreground cursor-pointer transition-colors aria-selected:bg-primary/5 aria-selected:text-foreground"
                  >
                    <span className="text-muted-foreground">{item.icon}</span>
                    {item.label}
                  </Command.Item>
                ))}
              </Command.Group>
            )}

            {actionItems.length > 0 && (
              <Command.Group
                heading="Actions"
                className="[&_[cmdk-group-heading]]:px-2 [&_[cmdk-group-heading]]:py-1.5 [&_[cmdk-group-heading]]:text-xs [&_[cmdk-group-heading]]:font-semibold [&_[cmdk-group-heading]]:text-muted-foreground [&_[cmdk-group-heading]]:uppercase [&_[cmdk-group-heading]]:tracking-wider"
              >
                {actionItems.map((item) => (
                  <Command.Item
                    key={item.id}
                    value={`${item.label} ${item.keywords || ""}`}
                    onSelect={() => {
                      item.action();
                      setOpen(false);
                    }}
                    className="flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm text-muted-foreground cursor-pointer transition-colors aria-selected:bg-primary/5 aria-selected:text-foreground"
                  >
                    <span className="text-muted-foreground">{item.icon}</span>
                    {item.label}
                  </Command.Item>
                ))}
              </Command.Group>
            )}
          </Command.List>

          {/* Footer */}
          <div className="flex items-center justify-between border-t border-border px-4 py-2">
            <div className="flex items-center gap-3 text-xs text-muted-foreground">
              <span className="flex items-center gap-1">
                <kbd className="rounded border border-border bg-muted px-1 py-0.5 text-xs font-mono">↑↓</kbd>
                Navigate
              </span>
              <span className="flex items-center gap-1">
                <kbd className="rounded border border-border bg-muted px-1 py-0.5 text-xs font-mono">↵</kbd>
                Select
              </span>
            </div>
            <span className="text-xs text-muted-foreground/60">
              <kbd className="font-mono">⌘K</kbd> to toggle
            </span>
          </div>
        </Command>
      </div>
    </div>
  );
}
