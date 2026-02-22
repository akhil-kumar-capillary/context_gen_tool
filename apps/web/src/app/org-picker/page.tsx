"use client";

import { useState, useMemo } from "react";
import { useRouter } from "next/navigation";
import { useAuthStore } from "@/stores/auth-store";

export default function OrgPickerPage() {
  const router = useRouter();
  const { orgs, selectOrg, logout } = useAuthStore();
  const [search, setSearch] = useState("");

  const filteredOrgs = useMemo(() => {
    const sorted = [...orgs].sort((a, b) => a.name.localeCompare(b.name));
    if (!search.trim()) return sorted;
    const q = search.toLowerCase();
    return sorted.filter(
      (o) =>
        o.name.toLowerCase().includes(q) || String(o.id).includes(q)
    );
  }, [orgs, search]);

  const handleSelect = (orgId: number, orgName: string) => {
    selectOrg(orgId, orgName);
    router.push("/dashboard/contexts");
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-gradient-to-br from-blue-50 to-indigo-100">
      <div className="w-full max-w-lg rounded-xl bg-white p-8 shadow-lg">
        <div className="mb-6 flex items-center justify-between">
          <div>
            <h1 className="text-xl font-bold text-gray-900">
              Select Organization
            </h1>
            <p className="text-sm text-gray-500">
              Choose the org to work with
            </p>
          </div>
          <button
            onClick={logout}
            className="text-sm text-gray-500 hover:text-gray-700"
          >
            Sign out
          </button>
        </div>

        <input
          type="text"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search organizations..."
          className="mb-4 w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/20"
        />

        <div className="max-h-96 overflow-y-auto rounded-lg border border-gray-200">
          {filteredOrgs.length === 0 ? (
            <div className="px-4 py-8 text-center text-sm text-gray-400">
              No organizations found
            </div>
          ) : (
            filteredOrgs.map((org) => (
              <button
                key={org.id}
                onClick={() => handleSelect(org.id, org.name)}
                className="flex w-full items-center justify-between border-b border-gray-100 px-4 py-3 text-left transition-colors last:border-0 hover:bg-blue-50"
              >
                <span className="text-sm font-medium text-gray-900">
                  {org.name}
                </span>
                <span className="text-xs text-gray-400">{org.id}</span>
              </button>
            ))
          )}
        </div>
      </div>
    </div>
  );
}
