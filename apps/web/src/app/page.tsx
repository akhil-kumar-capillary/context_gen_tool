"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuthStore } from "@/stores/auth-store";

export default function Home() {
  const router = useRouter();
  const { isLoggedIn, orgId } = useAuthStore();

  useEffect(() => {
    if (!isLoggedIn) {
      router.replace("/login");
    } else if (!orgId) {
      router.replace("/org-picker");
    } else {
      router.replace("/dashboard/contexts");
    }
  }, [isLoggedIn, orgId, router]);

  return (
    <div className="flex h-screen items-center justify-center">
      <div className="animate-spin h-8 w-8 border-4 border-primary border-t-transparent rounded-full" />
    </div>
  );
}
