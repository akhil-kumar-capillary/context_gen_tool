"use client";

import { useEffect, useState, useRef, useCallback } from "react";
import { useAdminStore, PlatformVariable } from "@/stores/admin-store";
import { cn } from "@/lib/utils";
import {
  Search, Plus, ChevronDown, ChevronRight, Copy, Pencil, Trash2,
  Upload, Download, RefreshCw, Loader2, Check, X, Variable,
} from "lucide-react";
import { toast } from "sonner";
import { PlatformVariableSheet } from "./platform-variable-sheet";

const TYPE_BADGES: Record<string, { label: string; className: string }> = {
  string:  { label: "string",  className: "bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300" },
  number:  { label: "number",  className: "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300" },
  boolean: { label: "bool",    className: "bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300" },
  json:    { label: "json",    className: "bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-300" },
  url:     { label: "url",     className: "bg-cyan-100 text-cyan-700 dark:bg-cyan-900/30 dark:text-cyan-300" },
  text:    { label: "text",    className: "bg-gray-100 text-gray-700 dark:bg-gray-900/30 dark:text-gray-300" },
};

export function PlatformVariablesPanel() {
  const {
    platformVariables, platformVariableGroups, platformVarsLoading,
    fetchPlatformVariables, createPlatformVariable, updatePlatformVariable,
    deletePlatformVariable, importPlatformVariables, exportPlatformVariables,
  } = useAdminStore();

  const [searchTerm, setSearchTerm] = useState("");
  const [groupFilter, setGroupFilter] = useState<string>("all");
  const [collapsedGroups, setCollapsedGroups] = useState<Set<string>>(new Set());
  const [editingCell, setEditingCell] = useState<{ id: number; field: string } | null>(null);
  const [editValue, setEditValue] = useState("");
  const [confirmDeleteId, setConfirmDeleteId] = useState<number | null>(null);
  const [sheetOpen, setSheetOpen] = useState(false);
  const [sheetVariable, setSheetVariable] = useState<PlatformVariable | null>(null);
  const [savingId, setSavingId] = useState<number | null>(null);
  const editInputRef = useRef<HTMLInputElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    fetchPlatformVariables();
  }, [fetchPlatformVariables]);

  // Focus inline edit input when editing
  useEffect(() => {
    if (editingCell && editInputRef.current) {
      editInputRef.current.focus();
      editInputRef.current.select();
    }
  }, [editingCell]);

  // Filter variables by search and group
  const filtered = platformVariables.filter((v) => {
    if (groupFilter !== "all") {
      const varGroup = v.group_name || "Ungrouped";
      if (varGroup !== groupFilter) return false;
    }
    if (searchTerm) {
      const term = searchTerm.toLowerCase();
      return (
        v.key.toLowerCase().includes(term) ||
        (v.value || "").toLowerCase().includes(term) ||
        (v.description || "").toLowerCase().includes(term)
      );
    }
    return true;
  });

  // Group variables
  const grouped = filtered.reduce<Record<string, PlatformVariable[]>>((acc, v) => {
    const group = v.group_name || "Ungrouped";
    if (!acc[group]) acc[group] = [];
    acc[group].push(v);
    return acc;
  }, {});

  // Sort group names (Ungrouped last)
  const sortedGroups = Object.keys(grouped).sort((a, b) => {
    if (a === "Ungrouped") return 1;
    if (b === "Ungrouped") return -1;
    return a.localeCompare(b);
  });

  const toggleGroup = (group: string) => {
    setCollapsedGroups((prev) => {
      const next = new Set(prev);
      if (next.has(group)) next.delete(group);
      else next.add(group);
      return next;
    });
  };

  const handleCopy = (value: string | null) => {
    navigator.clipboard.writeText(value || "");
    toast.success("Copied to clipboard");
  };

  const startInlineEdit = (v: PlatformVariable) => {
    if (v.value_type === "json" || v.value_type === "text") {
      // Open sheet for complex types
      setSheetVariable(v);
      setSheetOpen(true);
      return;
    }
    setEditingCell({ id: v.id, field: "value" });
    setEditValue(v.value || "");
  };

  const saveInlineEdit = async (v: PlatformVariable) => {
    if (editValue === (v.value || "")) {
      setEditingCell(null);
      return;
    }
    setSavingId(v.id);
    const ok = await updatePlatformVariable(v.id, { value: editValue });
    setSavingId(null);
    if (ok) {
      setEditingCell(null);
      fetchPlatformVariables();
    }
  };

  const handleBooleanToggle = async (v: PlatformVariable) => {
    const newValue = v.value?.toLowerCase() === "true" ? "false" : "true";
    setSavingId(v.id);
    const ok = await updatePlatformVariable(v.id, { value: newValue });
    setSavingId(null);
    if (ok) fetchPlatformVariables();
  };

  const handleDelete = async (id: number) => {
    const ok = await deletePlatformVariable(id);
    setConfirmDeleteId(null);
    if (ok) fetchPlatformVariables();
  };

  const handleExport = async () => {
    const data = await exportPlatformVariables();
    if (!data) {
      toast.error("Export failed");
      return;
    }
    const blob = new Blob([JSON.stringify({ variables: data }, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "platform-variables.json";
    a.click();
    URL.revokeObjectURL(url);
    toast.success("Exported successfully");
  };

  const handleImportFile = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    try {
      const text = await file.text();
      const parsed = JSON.parse(text);
      const variables = parsed.variables || parsed;
      if (!Array.isArray(variables)) {
        toast.error("Invalid format: expected { variables: [...] }");
        return;
      }
      const result = await importPlatformVariables(variables, true);
      if (result) {
        toast.success(`Import: ${result.created} created, ${result.updated} updated`);
        if (result.errors.length > 0) {
          toast.warning(`${result.errors.length} errors during import`);
        }
        fetchPlatformVariables();
      }
    } catch {
      toast.error("Failed to parse import file");
    }
    // Reset file input
    if (fileInputRef.current) fileInputRef.current.value = "";
  };

  const handleSheetSave = useCallback(async (data: Partial<PlatformVariable> & { key: string; change_reason?: string }, isEdit: boolean) => {
    let ok: boolean;
    if (isEdit && sheetVariable) {
      ok = await updatePlatformVariable(sheetVariable.id, data);
    } else {
      ok = await createPlatformVariable(data);
    }
    if (ok) {
      setSheetOpen(false);
      setSheetVariable(null);
      fetchPlatformVariables();
    }
    return ok;
  }, [sheetVariable, updatePlatformVariable, createPlatformVariable, fetchPlatformVariables]);

  // Render value cell based on type
  const renderValue = (v: PlatformVariable) => {
    const isEditing = editingCell?.id === v.id;
    const isSaving = savingId === v.id;

    if (v.value_type === "boolean") {
      return (
        <button
          onClick={() => handleBooleanToggle(v)}
          disabled={isSaving}
          className={cn(
            "relative inline-flex h-5 w-9 shrink-0 cursor-pointer rounded-full transition-colors",
            v.value?.toLowerCase() === "true"
              ? "bg-primary"
              : "bg-muted-foreground/25",
          )}
        >
          <span
            className={cn(
              "pointer-events-none inline-block h-4 w-4 rounded-full bg-white shadow-sm transition-transform mt-0.5",
              v.value?.toLowerCase() === "true" ? "translate-x-4 ml-0.5" : "translate-x-0.5",
            )}
          />
        </button>
      );
    }

    if (isEditing) {
      return (
        <div className="flex items-center gap-1">
          <input
            ref={editInputRef}
            type={v.value_type === "number" ? "number" : "text"}
            value={editValue}
            onChange={(e) => setEditValue(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") saveInlineEdit(v);
              if (e.key === "Escape") setEditingCell(null);
            }}
            onBlur={() => saveInlineEdit(v)}
            className="h-7 w-full rounded border border-primary/50 bg-background px-2 text-sm outline-none focus:ring-1 focus:ring-primary"
          />
          {isSaving && <Loader2 className="h-3.5 w-3.5 animate-spin text-muted-foreground" />}
        </div>
      );
    }

    const displayValue = v.value || v.default_value || "";
    const isDefault = !v.value && v.default_value;

    if (v.value_type === "json" || v.value_type === "text") {
      return (
        <button
          onClick={() => startInlineEdit(v)}
          className="max-w-xs truncate text-left text-sm text-muted-foreground hover:text-foreground"
          title={displayValue}
        >
          {displayValue ? (
            <span className="font-mono text-xs">
              {displayValue.length > 50 ? displayValue.slice(0, 50) + "..." : displayValue}
            </span>
          ) : (
            <span className="italic text-muted-foreground/50">empty</span>
          )}
          {isDefault && <span className="ml-1 text-xs text-muted-foreground/50">(default)</span>}
        </button>
      );
    }

    return (
      <button
        onClick={() => startInlineEdit(v)}
        className="max-w-xs truncate text-left text-sm hover:text-primary cursor-text"
        title={displayValue}
      >
        <span className={cn("font-mono text-xs", !displayValue && "italic text-muted-foreground/50")}>
          {displayValue || "empty"}
        </span>
        {isDefault && <span className="ml-1 text-xs text-muted-foreground/50">(default)</span>}
      </button>
    );
  };

  return (
    <div className="space-y-4">
      {/* Toolbar */}
      <div className="flex flex-wrap items-center gap-3">
        {/* Search */}
        <div className="relative flex-1 min-w-[200px]">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <input
            type="text"
            placeholder="Search variables..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            className="h-9 w-full rounded-lg border border-input bg-background pl-9 pr-3 text-sm outline-none focus:ring-2 focus:ring-primary/30"
          />
        </div>

        {/* Group filter */}
        <select
          value={groupFilter}
          onChange={(e) => setGroupFilter(e.target.value)}
          className="h-9 rounded-lg border border-input bg-background px-3 text-sm outline-none focus:ring-2 focus:ring-primary/30"
        >
          <option value="all">All Groups</option>
          {platformVariableGroups.map((g) => (
            <option key={g.name} value={g.name}>
              {g.name} ({g.count})
            </option>
          ))}
        </select>

        {/* Import */}
        <input
          ref={fileInputRef}
          type="file"
          accept=".json"
          onChange={handleImportFile}
          className="hidden"
        />
        <button
          onClick={() => fileInputRef.current?.click()}
          className="flex h-9 items-center gap-1.5 rounded-lg border px-3 text-sm hover:bg-muted transition-colors"
        >
          <Upload className="h-3.5 w-3.5" />
          Import
        </button>

        {/* Export */}
        <button
          onClick={handleExport}
          className="flex h-9 items-center gap-1.5 rounded-lg border px-3 text-sm hover:bg-muted transition-colors"
        >
          <Download className="h-3.5 w-3.5" />
          Export
        </button>

        {/* Refresh */}
        <button
          onClick={() => fetchPlatformVariables()}
          disabled={platformVarsLoading}
          className="flex h-9 items-center gap-1.5 rounded-lg border px-3 text-sm hover:bg-muted transition-colors"
        >
          <RefreshCw className={cn("h-3.5 w-3.5", platformVarsLoading && "animate-spin")} />
        </button>

        {/* New Variable */}
        <button
          onClick={() => { setSheetVariable(null); setSheetOpen(true); }}
          className="flex h-9 items-center gap-1.5 rounded-lg bg-primary px-4 text-sm font-medium text-primary-foreground hover:bg-primary/90 transition-colors"
        >
          <Plus className="h-3.5 w-3.5" />
          New Variable
        </button>
      </div>

      {/* Loading */}
      {platformVarsLoading && platformVariables.length === 0 && (
        <div className="flex items-center justify-center py-12">
          <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
        </div>
      )}

      {/* Empty state */}
      {!platformVarsLoading && platformVariables.length === 0 && (
        <div className="flex flex-col items-center justify-center py-16 text-muted-foreground">
          <Variable className="h-10 w-10 mb-3 opacity-40" />
          <p className="text-sm font-medium">No platform variables yet</p>
          <p className="text-xs mt-1">Create your first variable to get started.</p>
        </div>
      )}

      {/* No results */}
      {!platformVarsLoading && platformVariables.length > 0 && filtered.length === 0 && (
        <div className="flex flex-col items-center justify-center py-12 text-muted-foreground">
          <Search className="h-8 w-8 mb-2 opacity-40" />
          <p className="text-sm">No variables match your search</p>
        </div>
      )}

      {/* Grouped tables */}
      {sortedGroups.map((group) => {
        const vars = grouped[group];
        const isCollapsed = collapsedGroups.has(group);

        return (
          <div key={group} className="rounded-lg border bg-card overflow-hidden">
            {/* Group header */}
            <button
              onClick={() => toggleGroup(group)}
              className="flex w-full items-center gap-2 px-4 py-2.5 text-sm font-medium hover:bg-muted/50 transition-colors"
            >
              {isCollapsed ? (
                <ChevronRight className="h-4 w-4 text-muted-foreground" />
              ) : (
                <ChevronDown className="h-4 w-4 text-muted-foreground" />
              )}
              <span>{group}</span>
              <span className="text-xs text-muted-foreground">({vars.length})</span>
            </button>

            {/* Table */}
            {!isCollapsed && (
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-t text-left text-xs text-muted-foreground">
                    <th className="px-4 py-2 font-medium w-[30%]">Key</th>
                    <th className="px-4 py-2 font-medium w-[35%]">Value</th>
                    <th className="px-4 py-2 font-medium w-[8%]">Type</th>
                    <th className="px-4 py-2 font-medium w-[17%]">Description</th>
                    <th className="px-4 py-2 font-medium w-[10%] text-right">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {vars.map((v) => (
                    <tr
                      key={v.id}
                      className="border-t hover:bg-muted/30 transition-colors"
                    >
                      <td className="px-4 py-2">
                        <span className="font-mono text-xs">{v.key}</span>
                      </td>
                      <td className="px-4 py-2">{renderValue(v)}</td>
                      <td className="px-4 py-2">
                        <span
                          className={cn(
                            "inline-block rounded-full px-2 py-0.5 text-[10px] font-medium",
                            TYPE_BADGES[v.value_type]?.className || "bg-gray-100 text-gray-700",
                          )}
                        >
                          {TYPE_BADGES[v.value_type]?.label || v.value_type}
                        </span>
                      </td>
                      <td className="px-4 py-2">
                        <span className="text-xs text-muted-foreground truncate block max-w-[180px]" title={v.description || ""}>
                          {v.description || ""}
                        </span>
                      </td>
                      <td className="px-4 py-2">
                        <div className="flex items-center justify-end gap-1">
                          {/* Copy */}
                          <button
                            onClick={() => handleCopy(v.value)}
                            className="rounded p-1 hover:bg-muted transition-colors"
                            title="Copy value"
                          >
                            <Copy className="h-3.5 w-3.5 text-muted-foreground" />
                          </button>
                          {/* Edit (sheet) */}
                          <button
                            onClick={() => { setSheetVariable(v); setSheetOpen(true); }}
                            className="rounded p-1 hover:bg-muted transition-colors"
                            title="Edit variable"
                          >
                            <Pencil className="h-3.5 w-3.5 text-muted-foreground" />
                          </button>
                          {/* Delete */}
                          {confirmDeleteId === v.id ? (
                            <div className="flex items-center gap-0.5">
                              <button
                                onClick={() => handleDelete(v.id)}
                                className="rounded p-1 hover:bg-red-100 dark:hover:bg-red-900/30 transition-colors"
                                title="Confirm delete"
                              >
                                <Check className="h-3.5 w-3.5 text-red-600" />
                              </button>
                              <button
                                onClick={() => setConfirmDeleteId(null)}
                                className="rounded p-1 hover:bg-muted transition-colors"
                                title="Cancel"
                              >
                                <X className="h-3.5 w-3.5 text-muted-foreground" />
                              </button>
                            </div>
                          ) : (
                            <button
                              onClick={() => setConfirmDeleteId(v.id)}
                              className="rounded p-1 hover:bg-red-100 dark:hover:bg-red-900/30 transition-colors"
                              title="Delete variable"
                            >
                              <Trash2 className="h-3.5 w-3.5 text-muted-foreground hover:text-red-600" />
                            </button>
                          )}
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        );
      })}

      {/* Sheet */}
      {sheetOpen && (
        <PlatformVariableSheet
          variable={sheetVariable}
          existingGroups={platformVariableGroups.map((g) => g.name)}
          onClose={() => { setSheetOpen(false); setSheetVariable(null); }}
          onSave={handleSheetSave}
        />
      )}
    </div>
  );
}
