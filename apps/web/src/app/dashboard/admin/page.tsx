"use client";

import { useAuthStore } from "@/stores/auth-store";
import { useRouter } from "next/navigation";
import { useEffect } from "react";

export default function AdminPage() {
  const router = useRouter();
  const { user } = useAuthStore();

  useEffect(() => {
    if (user && !user.isAdmin) {
      router.replace("/dashboard/contexts");
    }
  }, [user, router]);

  if (!user?.isAdmin) return null;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Admin Panel</h1>
        <p className="text-sm text-gray-500">
          Manage users, roles, permissions, and secrets.
        </p>
      </div>
      <div className="rounded-xl border border-gray-200 bg-white p-12 text-center">
        <p className="text-gray-400">
          Admin panel will be built in Phase 5.
        </p>
      </div>
    </div>
  );
}
