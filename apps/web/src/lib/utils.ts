import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/** Valid characters for context names. */
export const CONTEXT_NAME_REGEX = /^[a-zA-Z0-9 _:#()\-,]*$/;
export const CONTEXT_NAME_ERROR =
  "Name can only contain letters, numbers, spaces, and _ : # ( ) - ,";

/** Format an ISO date string for display. */
export function formatDate(iso: string | null): string {
  if (!iso) return "\u2014";
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return iso;
  }
}

/** Download all contexts as .md files bundled in a ZIP. */
export async function downloadAllContexts(
  contexts: { name: string; context: string }[],
  orgId?: string | number | null
) {
  if (!contexts.length) return;

  const JSZip = (await import("jszip")).default;
  const zip = new JSZip();
  const usedNames = new Set<string>();

  for (const ctx of contexts) {
    let filename =
      ctx.name.replace(/[<>:"/\\|?*]/g, "_").trim() || "untitled";
    if (usedNames.has(filename)) {
      let i = 2;
      while (usedNames.has(`${filename}_${i}`)) i++;
      filename = `${filename}_${i}`;
    }
    usedNames.add(filename);
    zip.file(`${filename}.md`, ctx.context || "");
  }

  const blob = await zip.generateAsync({ type: "blob" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  const safeName = String(orgId || "unknown").replace(/[<>:"/\\|?*\s]+/g, "_");
  a.download = `${safeName}_aira_contexts_${new Date().toISOString().slice(0, 10)}.zip`;
  a.click();
  URL.revokeObjectURL(url);
}
