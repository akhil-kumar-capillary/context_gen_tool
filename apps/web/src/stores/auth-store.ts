import { create } from "zustand";
import { persist } from "zustand/middleware";
import type { Org, User } from "@/types";

interface AuthState {
  token: string | null;
  user: User | null;
  isLoggedIn: boolean;
  orgs: Org[];
  orgId: number | null;
  orgName: string | null;
  cluster: string | null;
  baseUrl: string | null;

  setAuth: (token: string, user: User, cluster: string, baseUrl: string) => void;
  setOrgs: (orgs: Org[]) => void;
  selectOrg: (orgId: number, orgName: string) => void;
  setAllowedModules: (modules: string[]) => void;
  hasModuleAccess: (module: string) => boolean;
  logout: () => void;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set, get) => ({
      token: null,
      user: null,
      isLoggedIn: false,
      orgs: [],
      orgId: null,
      orgName: null,
      cluster: null,
      baseUrl: null,

      setAuth: (token, user, cluster, baseUrl) =>
        set({
          token,
          user,
          isLoggedIn: true,
          orgs: user.orgs,
          cluster,
          baseUrl,
        }),

      setOrgs: (orgs) => set({ orgs }),

      selectOrg: (orgId, orgName) => set({ orgId, orgName }),

      setAllowedModules: (modules) =>
        set((state) => ({
          user: state.user ? { ...state.user, allowedModules: modules } : null,
        })),

      hasModuleAccess: (module: string): boolean => {
        const { user } = get();
        if (!user) return false;
        if (user.isAdmin) return true;
        if (module === "general") return true;
        return user.allowedModules?.includes(module) ?? false;
      },

      logout: () =>
        set({
          token: null,
          user: null,
          isLoggedIn: false,
          orgs: [],
          orgId: null,
          orgName: null,
          cluster: null,
          baseUrl: null,
        }),
    }),
    {
      name: "aira-auth",
      partialize: (state) => ({
        token: state.token,
        user: state.user,
        isLoggedIn: state.isLoggedIn,
        orgs: state.orgs,
        orgId: state.orgId,
        orgName: state.orgName,
        cluster: state.cluster,
        baseUrl: state.baseUrl,
      }),
    }
  )
);
