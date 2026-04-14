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

  // Original values for cancel/revert
  const [original, setOriginal] = useState({ preset: "", light: "", dark: "", darkMode: false });

  // Load current theme
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
    applyThemePreview(p.light, p.dark);
  };

  const handleCustomChange = (field: "light" | "dark", value: string) => {
    if (field === "light") setLightHsl(value);
    else setDarkHsl(value);
    setIsCustom(true);
    setActivePreset("custom");
    applyThemePreview(
      field === "light" ? value : lightHsl,
      field === "dark" ? value : darkHsl,
    );
  };

  const handleSave = async () => {
    if (!token) return;
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
      setOriginal({ preset: activePreset, light: lightHsl, dark: darkHsl, darkMode: darkModeDefault });
      toast.success("Theme saved");
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
        <p className="text-xs text-muted-foreground mb-4">Choose a primary color for the platform. Changes are live-previewed.</p>
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
                    ? "border-primary ring-2 ring-primary/20 bg-primary/5"
                    : "border-border hover:border-primary/30 hover:bg-muted/50",
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
                {isActive && <Check className="h-4 w-4 text-primary ml-auto shrink-0" />}
              </button>
            );
          })}
        </div>
      </div>

      {/* Custom Color */}
      <div>
        <h3 className="text-sm font-semibold text-foreground mb-1">Custom Color</h3>
        <p className="text-xs text-muted-foreground mb-3">Enter HSL values for a custom primary color (hue saturation% lightness%).</p>
        <div className="flex gap-4">
          <div className="flex-1">
            <label className="text-xs font-medium text-muted-foreground mb-1 block">Light Mode</label>
            <div className="flex items-center gap-2">
              <div
                className="h-8 w-8 rounded-lg shrink-0 border border-border"
                style={{ backgroundColor: `hsl(${lightHsl})` }}
              />
              <input
                type="text"
                value={lightHsl}
                onChange={(e) => handleCustomChange("light", e.target.value)}
                placeholder="215 70% 55%"
                className="flex-1 rounded-lg border border-input bg-background px-3 py-1.5 text-sm font-mono"
              />
            </div>
          </div>
          <div className="flex-1">
            <label className="text-xs font-medium text-muted-foreground mb-1 block">Dark Mode</label>
            <div className="flex items-center gap-2">
              <div
                className="h-8 w-8 rounded-lg shrink-0 border border-border"
                style={{ backgroundColor: `hsl(${darkHsl})` }}
              />
              <input
                type="text"
                value={darkHsl}
                onChange={(e) => handleCustomChange("dark", e.target.value)}
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
      <div className="flex items-center gap-3 pt-2 border-t border-border">
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
