"use client";

import { useAuthStore } from "@/stores/auth-store";
import { useRouter } from "next/navigation";
import { LogOut, Building2 } from "lucide-react";

export function DashboardHeader() {
  const router = useRouter();
  const { user, orgName, orgId, logout } = useAuthStore();

  const handleSwitchOrg = () => {
    router.push("/org-picker");
  };

  const handleLogout = () => {
    logout();
    router.push("/login");
  };

  return (
    <header className="flex h-14 items-center justify-between border-b border-gray-200 bg-white px-6">
      <div className="flex items-center gap-3">
        <button
          onClick={handleSwitchOrg}
          className="flex items-center gap-2 rounded-lg border border-gray-200 px-3 py-1.5 text-sm transition-colors hover:bg-gray-50"
        >
          <Building2 className="h-3.5 w-3.5 text-gray-500" />
          <span className="font-medium text-gray-700">{orgName}</span>
          <span className="text-xs text-gray-400">({orgId})</span>
        </button>
      </div>

      <div className="flex items-center gap-4">
        <span className="text-sm text-gray-500">{user?.email}</span>
        <button
          onClick={handleLogout}
          className="flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm text-gray-500 transition-colors hover:bg-gray-100 hover:text-gray-700"
        >
          <LogOut className="h-3.5 w-3.5" />
          Sign out
        </button>
      </div>
    </header>
  );
}
