"use client";

import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Loader2, RotateCcw, Check } from "lucide-react";
import { cn } from "@/lib/utils";
import { apiClient } from "@/lib/api-client";
import { useAuthStore } from "@/stores/auth-store";
import { applyThemePreview } from "@/components/shared/theme-loader";

interface ThemePreset {
  light: string;
  dark: string;
}

const PRESET_ORDER = [
  { id: "slate_blue", label: "Slate Blue" },
  { id: "indigo", label: "Indigo" },
  { id: "teal", label: "Teal" },
  { id: "emerald", label: "Emerald" },
  { id: "rose", label: "Rose" },
  { id: "amber", label: "Amber" },
];

// ── HSL ↔ Hex converters ───────────────────────────────────────────

function hslToHex(hslStr: string): string {
  const parts = hslStr.match(/[\d.]+/g);
  if (!parts || parts.length < 3) return "#6366f1";
  const h = parseFloat(parts[0]) / 360;
  const s = parseFloat(parts[1]) / 100;
  const l = parseFloat(parts[2]) / 100;

  const hue2rgb = (p: number, q: number, t: number) => {
    if (t < 0) t += 1;
    if (t > 1) t -= 1;
    if (t < 1 / 6) return p + (q - p) * 6 * t;
    if (t < 1 / 2) return q;
    if (t < 2 / 3) return p + (q - p) * (2 / 3 - t) * 6;
    return p;
  };

  let r: number, g: number, b: number;
  if (s === 0) {
    r = g = b = l;
  } else {
    const q = l < 0.5 ? l * (1 + s) : l + s - l * s;
    const p = 2 * l - q;
    r = hue2rgb(p, q, h + 1 / 3);
    g = hue2rgb(p, q, h);
    b = hue2rgb(p, q, h - 1 / 3);
  }

  const toHex = (x: number) => Math.round(x * 255).toString(16).padStart(2, "0");
  return `#${toHex(r)}${toHex(g)}${toHex(b)}`;
}

function hexToHsl(hex: string): string {
  const result = /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(hex);
  if (!result) return "215 70% 55%";
  const r = parseInt(result[1], 16) / 255;
  const g = parseInt(result[2], 16) / 255;
  const b = parseInt(result[3], 16) / 255;

  const max = Math.max(r, g, b);
  const min = Math.min(r, g, b);
  let h = 0;
  let s = 0;
  const l = (max + min) / 2;

  if (max !== min) {
    const d = max - min;
    s = l > 0.5 ? d / (2 - max - min) : d / (max + min);
    switch (max) {
      case r: h = ((g - b) / d + (g < b ? 6 : 0)) / 6; break;
      case g: h = ((b - r) / d + 2) / 6; break;
      case b: h = ((r - g) / d + 4) / 6; break;
    }
  }

  return `${Math.round(h * 360)} ${Math.round(s * 100)}% ${Math.round(l * 100)}%`;
}

// ── Component ──────────────────────────────────────────────────────

export function CustomizationPanel() {
  const { token } = useAuthStore();

  const [presets, setPresets] = useState<Record<string, ThemePreset>>({});
  const [activePreset, setActivePreset] = useState("slate_blue");
  const [lightHsl, setLightHsl] = useState("215 70% 55%");
  const [darkHsl, setDarkHsl] = useState("215 70% 65%");
  const [darkModeDefault, setDarkModeDefault] = useState(false);
  const [isCustom, setIsCustom] = useState(false);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [resetting, setResetting] = useState(false);

  const [original, setOriginal] = useState({ preset: "", light: "", dark: "", darkMode: false });

  useEffect(() => {
    if (!token) return;
    apiClient
      .get<{
        theme_preset: string;
        primary_hsl_light: string;
        primary_hsl_dark: string;
        dark_mode_default: boolean;
        presets: Record<string, ThemePreset>;
      }>("/api/admin/theme", { token })
      .then((data) => {
        setPresets(data.presets);
        setActivePreset(data.theme_preset);
        setLightHsl(data.primary_hsl_light);
        setDarkHsl(data.primary_hsl_dark);
        setDarkModeDefault(data.dark_mode_default);
        setIsCustom(!data.presets[data.theme_preset]);
        setOriginal({
          preset: data.theme_preset,
          light: data.primary_hsl_light,
          dark: data.primary_hsl_dark,
          darkMode: data.dark_mode_default,
        });
      })
      .finally(() => setLoading(false));
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  const selectPreset = (id: string) => {
    const p = presets[id];
    if (!p) return;
    setActivePreset(id);
    setLightHsl(p.light);
    setDarkHsl(p.dark);
    setIsCustom(false);
    // NO live preview — only apply on save
  };

  const handleHslChange = (field: "light" | "dark", value: string) => {
    if (field === "light") setLightHsl(value);
    else setDarkHsl(value);
    setIsCustom(true);
    setActivePreset("custom");
  };

  const handleColorPicker = (field: "light" | "dark", hex: string) => {
    const hsl = hexToHsl(hex);
    handleHslChange(field, hsl);
  };

  const isValidHsl = (v: string) => /^\d{1,3}\s+\d{1,3}%\s+\d{1,3}%$/.test(v.trim());

  const handleSave = async () => {
    if (!token) return;
    if (!isValidHsl(lightHsl) || !isValidHsl(darkHsl)) {
      toast.error("Invalid HSL format. Use: hue saturation% lightness% (e.g. 215 70% 55%)");
      return;
    }
    setSaving(true);
    try {
      await apiClient.put(
        "/api/admin/theme",
        {
          theme_preset: isCustom ? "custom" : activePreset,
          primary_hsl_light: lightHsl,
          primary_hsl_dark: darkHsl,
          dark_mode_default: darkModeDefault,
        },
        { token },
      );
      // Apply globally ONLY after successful save
      applyThemePreview(lightHsl, darkHsl);
      setOriginal({ preset: activePreset, light: lightHsl, dark: darkHsl, darkMode: darkModeDefault });
      toast.success("Theme saved — all users will see this change");
    } catch {
      toast.error("Failed to save theme");
    }
    setSaving(false);
  };

  const handleReset = async () => {
    if (!token) return;
    setResetting(true);
    try {
      await apiClient.post("/api/admin/theme/reset", {}, { token });
      const def = presets["slate_blue"];
      if (def) {
        setActivePreset("slate_blue");
        setLightHsl(def.light);
        setDarkHsl(def.dark);
        setDarkModeDefault(false);
        setIsCustom(false);
        applyThemePreview(def.light, def.dark);
        setOriginal({ preset: "slate_blue", light: def.light, dark: def.dark, darkMode: false });
      }
      toast.success("Theme reset to Slate Blue");
    } catch {
      toast.error("Failed to reset theme");
    }
    setResetting(false);
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
      </div>
    );
  }

  const hasChanges =
    activePreset !== original.preset ||
    lightHsl !== original.light ||
    darkHsl !== original.dark ||
    darkModeDefault !== original.darkMode;

  return (
    <div className="max-w-2xl space-y-8">
      {/* Presets */}
      <div>
        <h3 className="text-sm font-semibold text-foreground mb-1">Color Presets</h3>
        <p className="text-xs text-muted-foreground mb-4">Choose a primary color for the platform. Click Save to apply.</p>
        <div className="grid grid-cols-3 gap-3">
          {PRESET_ORDER.map((p) => {
            const preset = presets[p.id];
            if (!preset) return null;
            const isActive = activePreset === p.id && !isCustom;
            return (
              <button
                key={p.id}
                onClick={() => selectPreset(p.id)}
                className={cn(
                  "flex items-center gap-3 rounded-xl border p-3 transition-all text-left",
                  isActive
                    ? "border-foreground/30 ring-2 ring-foreground/10 bg-muted/50"
                    : "border-border hover:border-foreground/20 hover:bg-muted/30",
                )}
              >
                <div
                  className="h-8 w-8 rounded-full shrink-0 shadow-sm"
                  style={{ backgroundColor: `hsl(${preset.light})` }}
                />
                <div>
                  <p className="text-sm font-medium text-foreground">{p.label}</p>
                  <p className="text-xs text-muted-foreground font-mono">{preset.light}</p>
                </div>
                {isActive && <Check className="h-4 w-4 text-foreground ml-auto shrink-0" />}
              </button>
            );
          })}
        </div>
      </div>

      {/* Custom Color with Picker */}
      <div>
        <h3 className="text-sm font-semibold text-foreground mb-1">Custom Color</h3>
        <p className="text-xs text-muted-foreground mb-3">Use the color picker or enter HSL values manually.</p>
        <div className="flex gap-6">
          <div className="flex-1">
            <label className="text-xs font-medium text-muted-foreground mb-1.5 block">Light Mode</label>
            <div className="flex items-center gap-2">
              <label className="relative cursor-pointer">
                <input
                  type="color"
                  value={hslToHex(lightHsl)}
                  onChange={(e) => handleColorPicker("light", e.target.value)}
                  className="absolute inset-0 opacity-0 cursor-pointer"
                />
                <div
                  className="h-9 w-9 rounded-lg shrink-0 border-2 border-border hover:border-foreground/30 transition-colors"
                  style={{ backgroundColor: `hsl(${lightHsl})` }}
                />
              </label>
              <input
                type="text"
                value={lightHsl}
                onChange={(e) => handleHslChange("light", e.target.value)}
                placeholder="215 70% 55%"
                className="flex-1 rounded-lg border border-input bg-background px-3 py-1.5 text-sm font-mono"
              />
            </div>
          </div>
          <div className="flex-1">
            <label className="text-xs font-medium text-muted-foreground mb-1.5 block">Dark Mode</label>
            <div className="flex items-center gap-2">
              <label className="relative cursor-pointer">
                <input
                  type="color"
                  value={hslToHex(darkHsl)}
                  onChange={(e) => handleColorPicker("dark", e.target.value)}
                  className="absolute inset-0 opacity-0 cursor-pointer"
                />
                <div
                  className="h-9 w-9 rounded-lg shrink-0 border-2 border-border hover:border-foreground/30 transition-colors"
                  style={{ backgroundColor: `hsl(${darkHsl})` }}
                />
              </label>
              <input
                type="text"
                value={darkHsl}
                onChange={(e) => handleHslChange("dark", e.target.value)}
                placeholder="215 70% 65%"
                className="flex-1 rounded-lg border border-input bg-background px-3 py-1.5 text-sm font-mono"
              />
            </div>
          </div>
        </div>
      </div>

      {/* Dark Mode Default */}
      <div>
        <h3 className="text-sm font-semibold text-foreground mb-1">Dark Mode Default</h3>
        <p className="text-xs text-muted-foreground mb-3">When enabled, new users will see dark mode by default.</p>
        <label className="flex items-center gap-3 cursor-pointer">
          <button
            onClick={() => setDarkModeDefault(!darkModeDefault)}
            className={cn(
              "relative h-6 w-11 rounded-full transition-colors",
              darkModeDefault ? "bg-primary" : "bg-muted",
            )}
          >
            <span
              className={cn(
                "absolute top-0.5 left-0.5 h-5 w-5 rounded-full bg-background shadow transition-transform",
                darkModeDefault && "translate-x-5",
              )}
            />
          </button>
          <span className="text-sm text-foreground">
            {darkModeDefault ? "Dark mode is the default" : "System preference (default)"}
          </span>
        </label>
      </div>

      {/* Actions */}
      <div className="flex items-center gap-3 pt-4 border-t border-border">
        <button
          onClick={handleReset}
          disabled={resetting}
          className="flex items-center gap-1.5 rounded-lg border border-border px-4 py-2 text-sm font-medium text-muted-foreground transition-colors hover:bg-muted hover:text-foreground disabled:opacity-50"
        >
          {resetting ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <RotateCcw className="h-3.5 w-3.5" />}
          Reset to Default
        </button>
        <button
          onClick={handleSave}
          disabled={saving || !hasChanges}
          className="flex items-center gap-1.5 rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground transition-colors hover:bg-primary/90 disabled:opacity-50"
        >
          {saving ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Check className="h-3.5 w-3.5" />}
          Save Changes
        </button>
        {hasChanges && (
          <span className="text-xs text-muted-foreground">Unsaved changes</span>
        )}
      </div>
    </div>
  );
}
