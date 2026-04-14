"use client";

import { useEffect } from "react";
import { useTheme } from "next-themes";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "";

/**
 * Fetches the platform theme from the backend on mount
 * and applies CSS variables globally. Falls back to CSS defaults on error.
 */
export function ThemeLoader() {
  const { setTheme } = useTheme();

  useEffect(() => {
    const isValidHsl = (v: unknown): v is string =>
      typeof v === "string" && /^\d{1,3}\s+\d{1,3}%\s+\d{1,3}%$/.test(v);

    fetch(`${API_BASE}/api/admin/theme`)
      .then((r) => r.json())
      .then((theme) => {
        const light = isValidHsl(theme.primary_hsl_light) ? theme.primary_hsl_light : null;
        const dark = isValidHsl(theme.primary_hsl_dark) ? theme.primary_hsl_dark : null;

        if (light) {
          document.documentElement.style.setProperty("--primary", light);
          document.documentElement.style.setProperty("--ring", light);
        }
        if (dark) {
          const id = "theme-dark-override";
          let el = document.getElementById(id) as HTMLStyleElement | null;
          if (!el) {
            el = document.createElement("style");
            el.id = id;
            document.head.appendChild(el);
          }
          el.textContent = `.dark { --primary: ${dark}; --ring: ${dark}; }`;
        }

        // Apply dark mode default for users who haven't explicitly chosen
        if (theme.dark_mode_default) {
          const userHasChosen = localStorage.getItem("theme");
          if (!userHasChosen) {
            setTheme("dark");
          }
        }
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
