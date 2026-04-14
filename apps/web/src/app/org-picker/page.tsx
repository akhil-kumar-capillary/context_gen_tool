"use client";

import { useState, useMemo } from "react";
import { useRouter } from "next/navigation";
import { useAuthStore } from "@/stores/auth-store";
import { Search, ChevronRight, LogOut, Building2 } from "lucide-react";

export default function OrgPickerPage() {
  const router = useRouter();
  const { orgs, user, selectOrg, logout } = useAuthStore();
  const [search, setSearch] = useState("");

  const filteredOrgs = useMemo(() => {
    const sorted = [...orgs].sort((a, b) => a.name.localeCompare(b.name));
    if (!search.trim()) return sorted;
    const q = search.toLowerCase();
    return sorted.filter(
      (o) =>
        o.name.toLowerCase().includes(q) || String(o.id).includes(q),
    );
  }, [orgs, search]);

  const handleSelect = (orgId: number, orgName: string) => {
    selectOrg(orgId, orgName);
    router.push("/dashboard/contexts");
  };

  const handleLogout = () => {
    logout();
    localStorage.removeItem("aira-auth");
    window.location.href = "/login";
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-muted/30 p-4">
      <div className="w-full max-w-lg">
        {/* Card */}
        <div className="rounded-2xl bg-background shadow-lg border border-border overflow-hidden">
          {/* Header */}
          <div className="px-8 pt-8 pb-6 text-center">
            <img
              src="/aira-logo.png"
              alt="aiRA"
              className="mx-auto mb-4 h-16 w-auto drop-shadow-lg"
            />
            <h1 className="text-xl font-bold text-foreground">
              Welcome back{user?.displayName ? `, ${user.displayName.split(" ")[0]}` : ""}
            </h1>
            <p className="mt-1 text-sm text-muted-foreground">
              Select an organization to continue
            </p>
          </div>

          {/* Search */}
          <div className="px-6 pb-4">
            <div className="relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
              <input
                type="text"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Search organizations..."
                className="w-full rounded-xl border border-input bg-muted/30 pl-10 pr-4 py-2.5 text-sm transition-colors focus:bg-background"
              />
            </div>
          </div>

          {/* Org list */}
          <div className="max-h-80 overflow-y-auto px-6 pb-2">
            {filteredOrgs.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-10">
                <Building2 className="h-8 w-8 text-muted-foreground/40 mb-2" />
                <p className="text-sm text-muted-foreground">
                  No organizations match your search
                </p>
              </div>
            ) : (
              <div className="space-y-2">
                {filteredOrgs.map((org) => (
                  <button
                    key={org.id}
                    onClick={() => handleSelect(org.id, org.name)}
                    className="flex w-full items-center justify-between rounded-xl border border-border p-4 text-left transition-all hover:border-primary/30 hover:bg-primary/5 hover:shadow-sm group"
                  >
                    <div>
                      <p className="text-sm font-semibold text-foreground group-hover:text-primary transition-colors">
                        {org.name}
                      </p>
                      <p className="text-xs text-muted-foreground mt-0.5">
                        ID: {org.id}
                      </p>
                    </div>
                    <ChevronRight className="h-4 w-4 text-muted-foreground/40 group-hover:text-primary transition-colors" />
                  </button>
                ))}
              </div>
            )}
          </div>

          {/* Footer */}
          <div className="border-t border-border px-8 py-4">
            <button
              onClick={handleLogout}
              className="flex w-full items-center justify-center gap-2 rounded-lg py-2 text-sm text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
            >
              <LogOut className="h-3.5 w-3.5" />
              Sign out
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
