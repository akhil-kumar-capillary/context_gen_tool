"use client";

import { useState, useEffect, useRef } from "react";
import { motion } from "framer-motion";
import { X, Loader2, AlertCircle, ChevronDown } from "lucide-react";
import { cn } from "@/lib/utils";
import type { PlatformVariable } from "@/stores/admin-store";

const VALUE_TYPES = [
  { value: "string", label: "String" },
  { value: "number", label: "Number" },
  { value: "boolean", label: "Boolean" },
  { value: "json", label: "JSON" },
  { value: "url", label: "URL" },
  { value: "text", label: "Text (multiline)" },
];

interface Props {
  variable: PlatformVariable | null; // null = create mode
  existingGroups: string[];
  onClose: () => void;
  onSave: (data: Record<string, unknown> & { key: string }, isEdit: boolean) => Promise<boolean>;
}

export function PlatformVariableSheet({ variable, existingGroups, onClose, onSave }: Props) {
  const isEdit = !!variable;

  const [key, setKey] = useState(variable?.key || "");
  const [value, setValue] = useState(variable?.value || "");
  const [valueType, setValueType] = useState<PlatformVariable["value_type"]>(variable?.value_type || "string");
  const [groupName, setGroupName] = useState(variable?.group_name || "");
  const [description, setDescription] = useState(variable?.description || "");
  const [defaultValue, setDefaultValue] = useState(variable?.default_value || "");
  const [isRequired, setIsRequired] = useState(variable?.is_required || false);
  const [validationRule, setValidationRule] = useState(variable?.validation_rule || "");
  const [sortOrder, setSortOrder] = useState(variable?.sort_order ?? 0);
  const [changeReason, setChangeReason] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [groupDropdownOpen, setGroupDropdownOpen] = useState(false);
  const groupRef = useRef<HTMLDivElement>(null);

  // Reset state when variable changes
  useEffect(() => {
    if (variable) {
      setKey(variable.key);
      setValue(variable.value || "");
      setValueType(variable.value_type);
      setGroupName(variable.group_name || "");
      setDescription(variable.description || "");
      setDefaultValue(variable.default_value || "");
      setIsRequired(variable.is_required);
      setValidationRule(variable.validation_rule || "");
      setSortOrder(variable.sort_order);
    }
  }, [variable]);

  // Close group dropdown on click outside
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (groupRef.current && !groupRef.current.contains(e.target as Node)) {
        setGroupDropdownOpen(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const filteredGroups = existingGroups
    .filter((g) => g !== "Ungrouped")
    .filter((g) => !groupName || g.toLowerCase().includes(groupName.toLowerCase()));

  const handleSave = async () => {
    setError(null);

    if (!key.trim()) {
      setError("Key is required");
      return;
    }
    if (!/^[a-zA-Z0-9/_\-\.]+$/.test(key)) {
      setError("Key must contain only letters, numbers, /, _, -, .");
      return;
    }
    if (isRequired && !value.trim() && !defaultValue.trim()) {
      setError("Value is required for this variable");
      return;
    }

    setSaving(true);
    const data: Record<string, unknown> & { key: string } = {
      key: key.trim(),
      value: value || null,
      value_type: valueType,
      group_name: groupName.trim() || null,
      description: description.trim() || null,
      default_value: defaultValue || null,
      is_required: isRequired,
      validation_rule: validationRule.trim() || null,
      sort_order: sortOrder,
    };
    if (isEdit && changeReason.trim()) {
      data.change_reason = changeReason.trim();
    }

    const ok = await onSave(data, isEdit);
    setSaving(false);
    if (!ok) {
      setError("Save failed — check the error message above");
    }
  };

  const renderValueInput = () => {
    switch (valueType) {
      case "boolean":
        return (
          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={() => setValue(value === "true" ? "false" : "true")}
              className={cn(
                "relative inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full transition-colors",
                value === "true" ? "bg-primary" : "bg-muted-foreground/25",
              )}
            >
              <span
                className={cn(
                  "pointer-events-none inline-block h-5 w-5 rounded-full bg-white shadow-sm transition-transform mt-0.5",
                  value === "true" ? "translate-x-5 ml-0.5" : "translate-x-0.5",
                )}
              />
            </button>
            <span className="text-sm text-muted-foreground">{value === "true" ? "true" : "false"}</span>
          </div>
        );
      case "json":
        return (
          <textarea
            value={value}
            onChange={(e) => setValue(e.target.value)}
            rows={8}
            className="w-full rounded-lg border border-input bg-background px-3 py-2 font-mono text-xs outline-none focus:ring-2 focus:ring-primary/30 resize-y"
            placeholder='{"key": "value"}'
          />
        );
      case "text":
        return (
          <textarea
            value={value}
            onChange={(e) => setValue(e.target.value)}
            rows={6}
            className="w-full rounded-lg border border-input bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-primary/30 resize-y"
            placeholder="Enter multiline text..."
          />
        );
      case "number":
        return (
          <input
            type="number"
            value={value}
            onChange={(e) => setValue(e.target.value)}
            className="h-9 w-full rounded-lg border border-input bg-background px-3 text-sm outline-none focus:ring-2 focus:ring-primary/30"
            placeholder="0"
          />
        );
      case "url":
        return (
          <input
            type="url"
            value={value}
            onChange={(e) => setValue(e.target.value)}
            className="h-9 w-full rounded-lg border border-input bg-background px-3 text-sm outline-none focus:ring-2 focus:ring-primary/30"
            placeholder="https://example.com"
          />
        );
      default:
        return (
          <input
            type="text"
            value={value}
            onChange={(e) => setValue(e.target.value)}
            className="h-9 w-full rounded-lg border border-input bg-background px-3 text-sm outline-none focus:ring-2 focus:ring-primary/30"
            placeholder="Enter value..."
          />
        );
    }
  };

  return (
    <div className="fixed inset-0 z-[60] flex justify-end bg-black/30 backdrop-blur-[2px]">
      <div className="flex-1" onClick={onClose} />

      <motion.div
        initial={{ x: "100%" }}
        animate={{ x: 0 }}
        exit={{ x: "100%" }}
        transition={{ type: "spring", stiffness: 300, damping: 30 }}
        className="flex w-full sm:w-3/4 lg:w-[480px] flex-col bg-background shadow-2xl"
      >
        {/* Header */}
        <div className="flex items-center justify-between border-b border-border px-6 py-4">
          <h2 className="text-base font-semibold text-foreground">
            {isEdit ? "Edit Variable" : "New Variable"}
          </h2>
          <button
            onClick={onClose}
            className="rounded-md p-1.5 text-muted-foreground hover:bg-muted hover:text-foreground"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto px-6 py-4 space-y-4">
          {/* Error */}
          {error && (
            <div className="flex items-center gap-2 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700 dark:border-red-800 dark:bg-red-950/30 dark:text-red-400">
              <AlertCircle className="h-4 w-4 shrink-0" />
              {error}
            </div>
          )}

          {/* Key */}
          <div>
            <label className="mb-1 block text-xs font-medium text-foreground">Key</label>
            <input
              type="text"
              value={key}
              onChange={(e) => setKey(e.target.value)}
              disabled={isEdit}
              className={cn(
                "h-9 w-full rounded-lg border border-input bg-background px-3 font-mono text-sm outline-none focus:ring-2 focus:ring-primary/30",
                isEdit && "opacity-60 cursor-not-allowed",
              )}
              placeholder="group/variable_name"
            />
            <p className="mt-1 text-[11px] text-muted-foreground">
              Use <code>/</code> for hierarchy (e.g. <code>llm/default_model</code>)
            </p>
          </div>

          {/* Value Type */}
          <div>
            <label className="mb-1 block text-xs font-medium text-foreground">Type</label>
            <select
              value={valueType}
              onChange={(e) => {
                setValueType(e.target.value as PlatformVariable["value_type"]);
                if (e.target.value === "boolean" && value !== "true" && value !== "false") {
                  setValue("false");
                }
              }}
              className="h-9 w-full rounded-lg border border-input bg-background px-3 text-sm outline-none focus:ring-2 focus:ring-primary/30"
            >
              {VALUE_TYPES.map((t) => (
                <option key={t.value} value={t.value}>{t.label}</option>
              ))}
            </select>
          </div>

          {/* Value */}
          <div>
            <label className="mb-1 block text-xs font-medium text-foreground">Value</label>
            {renderValueInput()}
          </div>

          {/* Group */}
          <div ref={groupRef} className="relative">
            <label className="mb-1 block text-xs font-medium text-foreground">Group</label>
            <div className="relative">
              <input
                type="text"
                value={groupName}
                onChange={(e) => {
                  setGroupName(e.target.value);
                  setGroupDropdownOpen(true);
                }}
                onFocus={() => setGroupDropdownOpen(true)}
                className="h-9 w-full rounded-lg border border-input bg-background px-3 pr-8 text-sm outline-none focus:ring-2 focus:ring-primary/30"
                placeholder="Type to create or pick existing group"
              />
              <button
                type="button"
                onClick={() => setGroupDropdownOpen(!groupDropdownOpen)}
                className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
              >
                <ChevronDown className={cn("h-4 w-4 transition-transform", groupDropdownOpen && "rotate-180")} />
              </button>
            </div>
            {groupDropdownOpen && filteredGroups.length > 0 && (
              <div className="absolute z-10 mt-1 w-full rounded-lg border border-input bg-background shadow-lg max-h-40 overflow-y-auto">
                {filteredGroups.map((g) => (
                  <button
                    key={g}
                    type="button"
                    onClick={() => {
                      setGroupName(g);
                      setGroupDropdownOpen(false);
                    }}
                    className={cn(
                      "w-full px-3 py-2 text-left text-sm hover:bg-muted transition-colors",
                      g === groupName && "bg-muted font-medium",
                    )}
                  >
                    {g}
                  </button>
                ))}
              </div>
            )}
            <p className="mt-1 text-[11px] text-muted-foreground">
              Pick an existing group or type a new name
            </p>
          </div>

          {/* Description */}
          <div>
            <label className="mb-1 block text-xs font-medium text-foreground">Description</label>
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={2}
              className="w-full rounded-lg border border-input bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-primary/30 resize-y"
              placeholder="What this variable controls..."
            />
          </div>

          {/* Default Value */}
          <div>
            <label className="mb-1 block text-xs font-medium text-foreground">Default Value</label>
            <input
              type="text"
              value={defaultValue}
              onChange={(e) => setDefaultValue(e.target.value)}
              className="h-9 w-full rounded-lg border border-input bg-background px-3 text-sm outline-none focus:ring-2 focus:ring-primary/30"
              placeholder="Fallback if value is empty"
            />
          </div>

          {/* Required + Sort Order row */}
          <div className="flex gap-4">
            <div className="flex items-center gap-2">
              <label className="text-xs font-medium text-foreground">Required</label>
              <button
                type="button"
                onClick={() => setIsRequired(!isRequired)}
                className={cn(
                  "relative inline-flex h-5 w-9 shrink-0 cursor-pointer rounded-full transition-colors",
                  isRequired ? "bg-primary" : "bg-muted-foreground/25",
                )}
              >
                <span
                  className={cn(
                    "pointer-events-none inline-block h-4 w-4 rounded-full bg-white shadow-sm transition-transform mt-0.5",
                    isRequired ? "translate-x-4 ml-0.5" : "translate-x-0.5",
                  )}
                />
              </button>
            </div>
            <div className="flex-1">
              <label className="mb-1 block text-xs font-medium text-foreground">Sort Order</label>
              <input
                type="number"
                value={sortOrder}
                onChange={(e) => setSortOrder(parseInt(e.target.value) || 0)}
                className="h-9 w-full rounded-lg border border-input bg-background px-3 text-sm outline-none focus:ring-2 focus:ring-primary/30"
              />
            </div>
          </div>

          {/* Validation Rule */}
          <div>
            <label className="mb-1 block text-xs font-medium text-foreground">Validation Rule (regex)</label>
            <input
              type="text"
              value={validationRule}
              onChange={(e) => setValidationRule(e.target.value)}
              className="h-9 w-full rounded-lg border border-input bg-background px-3 font-mono text-xs outline-none focus:ring-2 focus:ring-primary/30"
              placeholder="^[a-z]+$"
            />
          </div>

          {/* Change Reason (edit mode only) */}
          {isEdit && (
            <div>
              <label className="mb-1 block text-xs font-medium text-foreground">Change Reason</label>
              <textarea
                value={changeReason}
                onChange={(e) => setChangeReason(e.target.value)}
                rows={2}
                className="w-full rounded-lg border border-input bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-primary/30 resize-y"
                placeholder="Why is this being changed? (optional)"
              />
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-end gap-3 border-t border-border px-6 py-4">
          <button
            onClick={onClose}
            className="h-9 rounded-lg border px-4 text-sm hover:bg-muted transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={handleSave}
            disabled={saving}
            className="flex h-9 items-center gap-2 rounded-lg bg-primary px-4 text-sm font-medium text-primary-foreground hover:bg-primary/90 transition-colors disabled:opacity-50"
          >
            {saving && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
            {isEdit ? "Save Changes" : "Create Variable"}
          </button>
        </div>
      </motion.div>
    </div>
  );
}
