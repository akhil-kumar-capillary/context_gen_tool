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
  logout: () => void;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
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
