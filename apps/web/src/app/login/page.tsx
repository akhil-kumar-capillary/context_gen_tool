"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useAuthStore } from "@/stores/auth-store";
import { apiClient } from "@/lib/api-client";
import { CLUSTERS } from "@/types";
import type { LoginResponse } from "@/types";

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
    <div className="flex min-h-screen items-center justify-center bg-gradient-to-br from-blue-50 to-indigo-100">
      <div className="w-full max-w-md rounded-xl bg-white p-8 shadow-lg">
        <div className="mb-8 text-center">
          <h1 className="text-3xl font-bold text-gray-900">aiRA</h1>
          <p className="mt-2 text-sm text-gray-500">
            Context Management Platform
          </p>
        </div>

        <form onSubmit={handleLogin} className="space-y-5">
          <div>
            <label className="mb-1.5 block text-sm font-medium text-gray-700">
              Cluster
            </label>
            <select
              value={cluster}
              onChange={(e) => setCluster(e.target.value)}
              className="w-full rounded-lg border border-gray-300 bg-white px-3 py-2.5 text-sm focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/20"
            >
              {CLUSTERS.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.label}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="mb-1.5 block text-sm font-medium text-gray-700">
              Username
            </label>
            <input
              type="text"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              placeholder="your.email@capillarytech.com"
              required
              className="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/20"
            />
          </div>

          <div>
            <label className="mb-1.5 block text-sm font-medium text-gray-700">
              Password
            </label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              className="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/20"
            />
          </div>

          {error && (
            <div className="rounded-lg bg-red-50 px-4 py-3 text-sm text-red-600">
              {error}
            </div>
          )}

          <button
            type="submit"
            disabled={isLoading}
            className="w-full rounded-lg bg-primary px-4 py-2.5 text-sm font-medium text-white transition-colors hover:bg-primary/90 disabled:opacity-50"
          >
            {isLoading ? "Signing in..." : "Sign In"}
          </button>
        </form>

        <p className="mt-6 text-center text-xs text-gray-400">
          Sign in with your Capillary Intouch credentials
        </p>
      </div>
    </div>
  );
}
