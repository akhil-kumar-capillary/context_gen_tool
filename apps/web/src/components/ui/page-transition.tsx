"use client";

/**
 * Wraps page content with a subtle fade-in animation on mount.
 * Uses a CSS @keyframes animation that runs once on render.
 */
export function PageTransition({ children }: { children: React.ReactNode }) {
  return (
    <div
      className="opacity-0"
      style={{
        animation: "fadeIn 200ms ease-out forwards",
      }}
    >
      {children}
    </div>
  );
}
