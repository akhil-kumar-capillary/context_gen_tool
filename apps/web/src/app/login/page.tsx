"use client";

import { useState, useMemo } from "react";
import { useRouter } from "next/navigation";
import { useAuthStore } from "@/stores/auth-store";
import { apiClient } from "@/lib/api-client";
import { TypeAnimation } from "react-type-animation";
import { CLUSTERS } from "@/types";
import type { LoginResponse } from "@/types";
import { AiraLogo } from "@/components/shared/aira-icon";

export default function LoginPage() {
  const router = useRouter();
  const { setAuth, setAllowedModules } = useAuthStore();

  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [cluster, setCluster] = useState<string>(CLUSTERS[0].id);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsLoading(true);
    setError(null);

    try {
      const selectedCluster = CLUSTERS.find((c) => c.id === cluster)!;
      const response = await apiClient.post<LoginResponse>("/api/auth/login", {
        username,
        password,
        cluster: cluster,
      });

      setAuth(response.token, response.user, cluster, selectedCluster.url);

      // Fetch user's allowed modules
      try {
        const modulesResp = await apiClient.get<{ modules: string[] }>(
          "/api/auth/me/modules",
          { token: response.token }
        );
        setAllowedModules(modulesResp.modules);
      } catch {
        // Fallback: only chat is universally accessible
        setAllowedModules(["general"]);
      }

      router.push("/org-picker");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Login failed");
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="flex min-h-screen">
      {/* Left brand panel */}
      <div className="hidden lg:flex lg:w-1/2 flex-col justify-between items-center bg-gradient-to-br from-primary/90 to-primary px-12 py-12">
        <div />
        <div className="max-w-md text-center">
          {/* Logo */}
          <div className="mx-auto mb-6 flex h-24 w-24 items-center justify-center rounded-2xl bg-white/10 backdrop-blur-sm shadow-2xl">
            <AiraLogo className="h-16 w-16 drop-shadow-lg" />
          </div>
          <h1 className="text-4xl font-bold text-primary-foreground mb-3">aiRA</h1>
          <p className="text-base font-medium text-primary-foreground/70 uppercase tracking-widest mb-8">Context Management Platform</p>
          <TerminalTyper />
        </div>
        <p className="text-xs text-primary-foreground/40">Powered by Capillary Pulse</p>
      </div>

      {/* Right form panel */}
      <div className="flex flex-1 items-center justify-center bg-background p-6">
      <div className="w-full max-w-sm">
        <div className="mb-8">
          <h2 className="text-2xl font-bold text-foreground">Sign in</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            Use your Capillary Intouch credentials
          </p>
        </div>

        <form onSubmit={handleLogin} className="space-y-5">
          <div>
            <label className="mb-1.5 block text-sm font-medium text-foreground">
              Cluster
            </label>
            <select
              value={cluster}
              onChange={(e) => setCluster(e.target.value)}
              className="w-full rounded-lg border border-input bg-background px-3 py-2.5 text-sm focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/20"
            >
              {CLUSTERS.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.label}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="mb-1.5 block text-sm font-medium text-foreground">
              Username
            </label>
            <input
              type="text"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              placeholder="your.email@capillarytech.com"
              required
              className="w-full rounded-lg border border-input px-3 py-2.5 text-sm focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/20"
            />
          </div>

          <div>
            <label className="mb-1.5 block text-sm font-medium text-foreground">
              Password
            </label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              className="w-full rounded-lg border border-input px-3 py-2.5 text-sm focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/20"
            />
          </div>

          {error && (
            <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 font-medium">
              {error}
            </div>
          )}

          <button
            type="submit"
            disabled={isLoading}
            className="w-full rounded-lg bg-primary px-4 py-2.5 text-sm font-semibold text-primary-foreground transition-colors hover:bg-primary/90 disabled:opacity-50"
          >
            {isLoading ? "Signing in..." : "Sign In"}
          </button>
        </form>

      </div>
      </div>
    </div>
  );
}

const FACTS = [
  "Ask aiRA anything — it knows your entire context.",
  "One tree to organize all your knowledge.",
  "Every edit versioned. Compare. Restore. Anytime.",
  "Extract insights from Databricks notebooks automatically.",
  "Chat-driven context management — just ask, aiRA delivers.",
  "Role-based access. Your data, your rules.",
  "Confluence pages to context docs in one click.",
  "Smart deduplication — no two contexts say the same thing.",
  "Secret scanning built in. Sensitive data stays private.",
  "Sync your context tree to production with one button.",
  "AI organizes hundreds of contexts into a clean hierarchy.",
  "Side-by-side diff — see exactly what changed between versions.",
  "Health scores on every node. Spot stale content instantly.",
  "Conflict detection finds contradictions across your docs.",
  "Redundancy detector eliminates overlapping knowledge.",
  "SQL fingerprinting turns query patterns into documentation.",
  "Config API extraction — loyalty, campaigns, coupons, all mapped.",
  "Real-time progress — watch tree generation unfold live.",
  "Blueprint-based refactoring for consistent doc structure.",
  "Multi-source collection — Databricks, Confluence, APIs, manual.",
  "Optimistic locking — no lost edits from concurrent users.",
  "Chat tools that read, write, and restructure your tree.",
  "Natural language search across your entire context tree.",
  "Restore any version with one click. History never lost.",
  "Audit trail tracks every change, every user, every action.",
  "Dark mode. Because your eyes matter at 2 AM.",
  "Cmd+K — navigate anywhere in the app instantly.",
  "Works on mobile, tablet, and desktop. Fully responsive.",
];

function shuffle<T>(arr: T[]): T[] {
  const a = [...arr];
  for (let i = a.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [a[i], a[j]] = [a[j], a[i]];
  }
  return a;
}

function TerminalTyper() {
  // Shuffle once on mount — stays stable across re-renders
  const sequence = useMemo(() => {
    const shuffled = shuffle(FACTS);
    const seq: (string | number)[] = [];
    for (const fact of shuffled) {
      seq.push(fact, 2500, "", 400);
    }
    return seq;
  }, []);

  return (
    <div className="h-14 flex items-center justify-center rounded-lg bg-black/20 backdrop-blur-sm border border-primary-foreground/10 px-5">
      <span className="text-primary-foreground/40 font-mono text-sm mr-2 select-none">&gt;</span>
      <TypeAnimation
        sequence={sequence}
        wrapper="span"
        speed={40}
        deletionSpeed={70}
        repeat={Infinity}
        cursor={false}
        className="font-mono text-sm text-primary-foreground/90"
      />
      <span className="ml-0.5 inline-block w-2.5 h-5 bg-primary-foreground/80 animate-[blink_1s_step-end_infinite]" />
    </div>
  );
}
