"use client";

import { useEffect } from "react";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "";

/**
 * Fetches the platform theme from the backend on mount
 * and applies CSS variables globally. Falls back to CSS defaults on error.
 */
export function ThemeLoader() {
  useEffect(() => {
    fetch(`${API_BASE}/api/admin/theme`)
      .then((r) => r.json())
      .then((theme) => {
        // Apply light mode primary
        document.documentElement.style.setProperty("--primary", theme.primary_hsl_light);
        document.documentElement.style.setProperty("--ring", theme.primary_hsl_light);

        // Apply dark mode overrides via injected style
        const id = "theme-dark-override";
        let el = document.getElementById(id) as HTMLStyleElement | null;
        if (!el) {
          el = document.createElement("style");
          el.id = id;
          document.head.appendChild(el);
        }
        el.textContent = `.dark { --primary: ${theme.primary_hsl_dark}; --ring: ${theme.primary_hsl_dark}; }`;
      })
      .catch(() => {
        // Fallback to CSS defaults in globals.css
      });
  }, []);

  return null;
}

/**
 * Apply theme CSS variables instantly (for live preview in admin panel).
 */
export function applyThemePreview(light: string, dark: string) {
  document.documentElement.style.setProperty("--primary", light);
  document.documentElement.style.setProperty("--ring", light);

  const id = "theme-dark-override";
  let el = document.getElementById(id) as HTMLStyleElement | null;
  if (!el) {
    el = document.createElement("style");
    el.id = id;
    document.head.appendChild(el);
  }
  el.textContent = `.dark { --primary: ${dark}; --ring: ${dark}; }`;
}
