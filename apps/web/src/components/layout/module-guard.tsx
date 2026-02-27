"use client";

import { useRouter } from "next/navigation";
import { useAuthStore } from "@/stores/auth-store";
import { ShieldX } from "lucide-react";

interface ModuleGuardProps {
  module: string;
  children: React.ReactNode;
}

/**
 * Wraps a page component and blocks access if the user doesn't have
 * permission for the given module. Admins always pass. Falls back to
 * an "access denied" screen with a link back to Chat.
 */
export function ModuleGuard({ module, children }: ModuleGuardProps) {
  const router = useRouter();
  const { user } = useAuthStore();

  // Admin bypasses all checks
  if (user?.isAdmin) return <>{children}</>;

  // Chat is always accessible (no module guard needed)
  if (module === "general") {
    return <>{children}</>;
  }

  const modules = user?.allowedModules;
  if (modules && modules.includes(module)) {
    return <>{children}</>;
  }

  return (
    <div className="flex flex-col items-center justify-center h-[calc(100vh-8rem)] text-center">
      <ShieldX className="h-12 w-12 text-gray-300 mb-4" />
      <h2 className="text-lg font-semibold text-gray-700 mb-1">Access Denied</h2>
      <p className="text-sm text-gray-500 mb-6 max-w-md">
        You don&apos;t have permission to access this module.
        Contact your admin to request access.
      </p>
      <button
        onClick={() => router.push("/dashboard/chat")}
        className="rounded-lg bg-primary px-4 py-2 text-sm font-medium text-white hover:bg-primary/90 transition-colors"
      >
        Go to Chat
      </button>
    </div>
  );
}
