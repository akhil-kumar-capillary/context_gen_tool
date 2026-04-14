"use client";

import { useEditor, EditorContent } from "@tiptap/react";
import StarterKit from "@tiptap/starter-kit";
import Underline from "@tiptap/extension-underline";
import Link from "@tiptap/extension-link";
import TextAlign from "@tiptap/extension-text-align";
import Placeholder from "@tiptap/extension-placeholder";
import { Table } from "@tiptap/extension-table";
import { TableRow } from "@tiptap/extension-table-row";
import { TableCell } from "@tiptap/extension-table-cell";
import { TableHeader } from "@tiptap/extension-table-header";
import { useEffect, useRef, useState, useCallback } from "react";
import { cn } from "@/lib/utils";
import {
  Bold,
  Italic,
  Underline as UnderlineIcon,
  Strikethrough,
  Heading1,
  Heading2,
  Heading3,
  List,
  ListOrdered,
  AlignLeft,
  AlignCenter,
  AlignRight,
  AlignJustify,
  Link as LinkIcon,
  Link2Off,
  Table as TableIcon,
  Undo,
  Redo,
  RemoveFormatting,
  Plus,
  Trash2,
  Merge,
  SplitSquareHorizontal,
  ToggleRight,
} from "lucide-react";

interface RichTextEditorProps {
  value: string;
  onChange: (html: string) => void;
  placeholder?: string;
  readOnly?: boolean;
  className?: string;
}

// ── Toolbar button ────────────────────────────────────────────────

function ToolbarBtn({
  onClick,
  active,
  disabled,
  title,
  children,
}: {
  onClick: () => void;
  active?: boolean;
  disabled?: boolean;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      title={title}
      className={cn(
        "rounded p-1.5 transition-colors",
        active
          ? "bg-primary/10 text-primary"
          : "text-muted-foreground hover:bg-muted hover:text-foreground",
        disabled && "opacity-40 pointer-events-none",
      )}
    >
      {children}
    </button>
  );
}

function Separator() {
  return <div className="mx-1 h-5 w-px bg-border" />;
}

// ── Link popover ──────────────────────────────────────────────────

function LinkPopover({
  editor,
  onClose,
}: {
  editor: NonNullable<ReturnType<typeof useEditor>>;
  onClose: () => void;
}) {
  const existing = editor.getAttributes("link").href || "";
  const [url, setUrl] = useState(existing);
  const ref = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    inputRef.current?.focus();
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) onClose();
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [onClose]);

  const apply = () => {
    if (!url.trim()) {
      editor.chain().focus().unsetLink().run();
    } else {
      const href = /^https?:\/\//i.test(url.trim()) ? url.trim() : `https://${url.trim()}`;
      editor.chain().focus().extendMarkRange("link").setLink({ href }).run();
    }
    onClose();
  };

  return (
    <div
      ref={ref}
      className="absolute top-full left-0 z-50 mt-1 w-72 rounded-lg border border-border bg-popover p-3 shadow-md"
    >
      <label className="mb-1.5 block text-xs font-medium text-popover-foreground">URL</label>
      <input
        ref={inputRef}
        type="text"
        value={url}
        onChange={(e) => setUrl(e.target.value)}
        onKeyDown={(e) => { if (e.key === "Enter") apply(); if (e.key === "Escape") onClose(); }}
        placeholder="https://example.com"
        className="w-full rounded-md border border-input bg-background px-2.5 py-1.5 text-sm"
      />
      <div className="mt-2 flex justify-end gap-2">
        <button
          onClick={onClose}
          className="rounded-md px-3 py-1 text-xs text-muted-foreground hover:bg-muted"
        >
          Cancel
        </button>
        <button
          onClick={apply}
          className="rounded-md bg-primary px-3 py-1 text-xs font-medium text-primary-foreground hover:bg-primary/90"
        >
          Apply
        </button>
      </div>
    </div>
  );
}

// ── Table dropdown ────────────────────────────────────────────────

function TableDropdown({ editor }: { editor: NonNullable<ReturnType<typeof useEditor>> }) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    if (open) document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open]);

  const isInTable = editor.isActive("table");

  const items = isInTable
    ? [
        { label: "Add row below", action: () => editor.chain().focus().addRowAfter().run(), icon: Plus },
        { label: "Add row above", action: () => editor.chain().focus().addRowBefore().run(), icon: Plus },
        { label: "Add column right", action: () => editor.chain().focus().addColumnAfter().run(), icon: Plus },
        { label: "Add column left", action: () => editor.chain().focus().addColumnBefore().run(), icon: Plus },
        { label: "Merge cells", action: () => editor.chain().focus().mergeCells().run(), icon: Merge },
        { label: "Split cell", action: () => editor.chain().focus().splitCell().run(), icon: SplitSquareHorizontal },
        { label: "Toggle header cell", action: () => editor.chain().focus().toggleHeaderCell().run(), icon: ToggleRight },
        { label: "Delete row", action: () => editor.chain().focus().deleteRow().run(), icon: Trash2 },
        { label: "Delete column", action: () => editor.chain().focus().deleteColumn().run(), icon: Trash2 },
        { label: "Delete table", action: () => editor.chain().focus().deleteTable().run(), icon: Trash2 },
      ]
    : [
        {
          label: "Insert 3x3 table",
          action: () => editor.chain().focus().insertTable({ rows: 3, cols: 3, withHeaderRow: true }).run(),
          icon: TableIcon,
        },
        {
          label: "Insert 4x4 table",
          action: () => editor.chain().focus().insertTable({ rows: 4, cols: 4, withHeaderRow: true }).run(),
          icon: TableIcon,
        },
      ];

  return (
    <div className="relative" ref={ref}>
      <ToolbarBtn onClick={() => setOpen(!open)} active={isInTable} title="Table">
        <TableIcon className="h-4 w-4" />
      </ToolbarBtn>
      {open && (
        <div className="absolute top-full left-0 z-50 mt-1 min-w-[180px] rounded-lg border border-border bg-popover shadow-md py-1">
          {items.map((item) => (
            <button
              key={item.label}
              onClick={() => { item.action(); setOpen(false); }}
              className="flex w-full items-center gap-2 px-3 py-1.5 text-xs text-popover-foreground hover:bg-muted transition-colors"
            >
              <item.icon className="h-3.5 w-3.5" />
              {item.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

// ── Toolbar ───────────────────────────────────────────────────────

function Toolbar({ editor }: { editor: NonNullable<ReturnType<typeof useEditor>> }) {
  const [linkOpen, setLinkOpen] = useState(false);

  // Force re-render on every editor transaction so active states stay in sync
  const [, setTick] = useState(0);
  useEffect(() => {
    const bump = () => setTick((n) => n + 1);
    editor.on("transaction", bump);
    return () => { editor.off("transaction", bump); };
  }, [editor]);

  const I = "h-4 w-4";

  return (
    <div className="flex flex-wrap items-center gap-0.5 border-b border-border bg-muted/30 px-2 py-1.5">
      {/* Text formatting */}
      <ToolbarBtn onClick={() => editor.chain().focus().toggleBold().run()} active={editor.isActive("bold")} title="Bold (Ctrl+B)">
        <Bold className={I} />
      </ToolbarBtn>
      <ToolbarBtn onClick={() => editor.chain().focus().toggleItalic().run()} active={editor.isActive("italic")} title="Italic (Ctrl+I)">
        <Italic className={I} />
      </ToolbarBtn>
      <ToolbarBtn onClick={() => editor.chain().focus().toggleUnderline().run()} active={editor.isActive("underline")} title="Underline (Ctrl+U)">
        <UnderlineIcon className={I} />
      </ToolbarBtn>
      <ToolbarBtn onClick={() => editor.chain().focus().toggleStrike().run()} active={editor.isActive("strike")} title="Strikethrough">
        <Strikethrough className={I} />
      </ToolbarBtn>

      <Separator />

      {/* Headings */}
      <ToolbarBtn onClick={() => editor.chain().focus().toggleHeading({ level: 1 }).run()} active={editor.isActive("heading", { level: 1 })} title="Heading 1">
        <Heading1 className={I} />
      </ToolbarBtn>
      <ToolbarBtn onClick={() => editor.chain().focus().toggleHeading({ level: 2 }).run()} active={editor.isActive("heading", { level: 2 })} title="Heading 2">
        <Heading2 className={I} />
      </ToolbarBtn>
      <ToolbarBtn onClick={() => editor.chain().focus().toggleHeading({ level: 3 }).run()} active={editor.isActive("heading", { level: 3 })} title="Heading 3">
        <Heading3 className={I} />
      </ToolbarBtn>

      <Separator />

      {/* Lists */}
      <ToolbarBtn onClick={() => editor.chain().focus().toggleBulletList().run()} active={editor.isActive("bulletList")} title="Bullet list">
        <List className={I} />
      </ToolbarBtn>
      <ToolbarBtn onClick={() => editor.chain().focus().toggleOrderedList().run()} active={editor.isActive("orderedList")} title="Numbered list">
        <ListOrdered className={I} />
      </ToolbarBtn>

      <Separator />

      {/* Alignment */}
      <ToolbarBtn onClick={() => editor.chain().focus().setTextAlign("left").run()} active={editor.isActive({ textAlign: "left" })} title="Align left">
        <AlignLeft className={I} />
      </ToolbarBtn>
      <ToolbarBtn onClick={() => editor.chain().focus().setTextAlign("center").run()} active={editor.isActive({ textAlign: "center" })} title="Align center">
        <AlignCenter className={I} />
      </ToolbarBtn>
      <ToolbarBtn onClick={() => editor.chain().focus().setTextAlign("right").run()} active={editor.isActive({ textAlign: "right" })} title="Align right">
        <AlignRight className={I} />
      </ToolbarBtn>
      <ToolbarBtn onClick={() => editor.chain().focus().setTextAlign("justify").run()} active={editor.isActive({ textAlign: "justify" })} title="Justify">
        <AlignJustify className={I} />
      </ToolbarBtn>

      <Separator />

      {/* Link */}
      <div className="relative">
        {editor.isActive("link") ? (
          <ToolbarBtn onClick={() => editor.chain().focus().unsetLink().run()} active title="Remove link">
            <Link2Off className={I} />
          </ToolbarBtn>
        ) : (
          <ToolbarBtn onClick={() => setLinkOpen(!linkOpen)} title="Insert link">
            <LinkIcon className={I} />
          </ToolbarBtn>
        )}
        {linkOpen && <LinkPopover editor={editor} onClose={() => setLinkOpen(false)} />}
      </div>

      {/* Table */}
      <TableDropdown editor={editor} />

      <Separator />

      {/* History */}
      <ToolbarBtn onClick={() => editor.chain().focus().undo().run()} disabled={!editor.can().undo()} title="Undo (Ctrl+Z)">
        <Undo className={I} />
      </ToolbarBtn>
      <ToolbarBtn onClick={() => editor.chain().focus().redo().run()} disabled={!editor.can().redo()} title="Redo (Ctrl+Shift+Z)">
        <Redo className={I} />
      </ToolbarBtn>

      <Separator />

      {/* Clear formatting */}
      <ToolbarBtn onClick={() => editor.chain().focus().clearNodes().unsetAllMarks().run()} title="Clear formatting">
        <RemoveFormatting className={I} />
      </ToolbarBtn>
    </div>
  );
}

// ── Main component ────────────────────────────────────────────────

export function RichTextEditor({
  value,
  onChange,
  placeholder,
  readOnly = false,
  className,
}: RichTextEditorProps) {
  const lastHtml = useRef(value);

  const handleUpdate = useCallback(
    ({ editor }: { editor: { getHTML: () => string } }) => {
      const html = editor.getHTML();
      lastHtml.current = html;
      onChange(html);
    },
    [onChange],
  );

  const editor = useEditor({
    immediatelyRender: false,
    extensions: [
      StarterKit.configure({
        heading: { levels: [1, 2, 3] },
      }),
      Underline,
      Link.configure({
        openOnClick: false,
        autolink: true,
        HTMLAttributes: {
          target: "_blank",
          rel: "noopener noreferrer",
          class: "tiptap-link",
        },
      }),
      TextAlign.configure({
        types: ["heading", "paragraph"],
      }),
      Placeholder.configure({
        placeholder: placeholder || "Start writing...",
      }),
      Table.configure({
        resizable: true,
      }),
      TableRow,
      TableCell,
      TableHeader,
    ],
    content: value,
    editable: !readOnly,
    onUpdate: handleUpdate,
    editorProps: {
      attributes: {
        class: "prose prose-sm max-w-none focus:outline-none min-h-full px-3 py-2 text-sm text-foreground",
      },
    },
  });

  // Sync external value changes (e.g. reset from parent) without resetting cursor
  useEffect(() => {
    if (editor && value !== lastHtml.current) {
      lastHtml.current = value;
      editor.commands.setContent(value, { emitUpdate: false });
    }
  }, [editor, value]);

  // Sync readOnly changes
  useEffect(() => {
    if (editor) {
      editor.setEditable(!readOnly);
    }
  }, [editor, readOnly]);

  if (!editor) return null;

  return (
    <div className={cn("flex flex-col rounded-lg border border-input bg-background overflow-hidden", className)}>
      {!readOnly && <Toolbar editor={editor} />}
      <div className="flex-1 overflow-y-auto min-h-0">
        <EditorContent editor={editor} className="h-full [&_.tiptap]:min-h-full [&_.tiptap]:h-full" />
      </div>
    </div>
  );
}
