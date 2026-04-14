"use client";

import { useState, useCallback } from "react";
import { useAuthStore } from "@/stores/auth-store";
import { ModuleGuard } from "@/components/layout/module-guard";
import {
  Plug, Search, FolderOpen, Download, Loader2, RefreshCw,
  ChevronRight, FileText, Check, AlertCircle, ExternalLink,
} from "lucide-react";
import { cn } from "@/lib/utils";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface Space {
  key: string;
  name: string;
  type: string;
  url: string;
}

interface PageResult {
  id: string;
  title: string;
  space_key: string;
  excerpt?: string;
  url?: string;
}

interface PageDetail {
  id: string;
  title: string;
  space_key: string;
  space_name: string;
  content: string;
  version: number;
  url: string;
}

interface ExtractionResult {
  run_id: string;
  space_key: string;
  space_name: string;
  pages_extracted: number;
  content: Array<{ page_id: string; title: string; content_md: string; url: string }>;
}

type ActiveTab = "browse" | "search" | "extract";

export default function ConfluencePage() {
  const { token, orgId } = useAuthStore();

  // Connection
  const [connected, setConnected] = useState<boolean | null>(null);
  const [connUrl, setConnUrl] = useState("");
  const [connLoading, setConnLoading] = useState(false);

  // Spaces
  const [spaces, setSpaces] = useState<Space[]>([]);
  const [spacesLoading, setSpacesLoading] = useState(false);

  // Browse
  const [selectedSpace, setSelectedSpace] = useState<Space | null>(null);
  const [spacePages, setSpacePages] = useState<PageResult[]>([]);
  const [browseLoading, setBrowseLoading] = useState(false);
  const [pageDetail, setPageDetail] = useState<PageDetail | null>(null);
  const [pageLoading, setPageLoading] = useState(false);

  // Search
  const [searchQuery, setSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState<PageResult[]>([]);
  const [searchLoading, setSearchLoading] = useState(false);

  // Extract
  const [extractSpace, setExtractSpace] = useState("");
  const [extractMaxPages, setExtractMaxPages] = useState(20);
  const [extracting, setExtracting] = useState(false);
  const [extraction, setExtraction] = useState<ExtractionResult | null>(null);

  // Tab
  const [activeTab, setActiveTab] = useState<ActiveTab>("browse");

  const headers = useCallback(
    () => ({
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
    }),
    [token]
  );

  // ── Actions ──

  const testConnection = async () => {
    setConnLoading(true);
    try {
      const resp = await fetch(`${API}/api/sources/confluence/test-connection`, {
        method: "POST",
        headers: headers(),
        body: JSON.stringify({}),
      });
      const data = await resp.json();
      setConnected(data.connected);
      setConnUrl(data.url || "");
    } catch {
      setConnected(false);
    }
    setConnLoading(false);
  };

  const loadSpaces = async () => {
    setSpacesLoading(true);
    try {
      const resp = await fetch(`${API}/api/sources/confluence/spaces?limit=100`, {
        headers: headers(),
      });
      const data = await resp.json();
      setSpaces(data.spaces || []);
    } catch {
      setSpaces([]);
    }
    setSpacesLoading(false);
  };

  const browseSpace = async (space: Space) => {
    setSelectedSpace(space);
    setPageDetail(null);
    setBrowseLoading(true);
    try {
      const resp = await fetch(
        `${API}/api/sources/confluence/spaces/${space.key}/pages?limit=50`,
        { headers: headers() }
      );
      const data = await resp.json();
      setSpacePages(data.pages || []);
    } catch {
      setSpacePages([]);
    }
    setBrowseLoading(false);
  };

  const loadPage = async (pageId: string) => {
    setPageLoading(true);
    try {
      const resp = await fetch(
        `${API}/api/sources/confluence/pages/${pageId}`,
        { headers: headers() }
      );
      const data = await resp.json();
      setPageDetail(data);
    } catch {
      setPageDetail(null);
    }
    setPageLoading(false);
  };

  const doSearch = async () => {
    if (!searchQuery.trim()) return;
    setSearchLoading(true);
    try {
      const resp = await fetch(`${API}/api/sources/confluence/search`, {
        method: "POST",
        headers: headers(),
        body: JSON.stringify({ query: searchQuery, limit: 15 }),
      });
      const data = await resp.json();
      setSearchResults(data.results || []);
    } catch {
      setSearchResults([]);
    }
    setSearchLoading(false);
  };

  const doExtract = async () => {
    if (!extractSpace.trim()) return;
    setExtracting(true);
    setExtraction(null);
    try {
      const resp = await fetch(
        `${API}/api/sources/confluence/extract?org_id=${orgId}`,
        {
          method: "POST",
          headers: headers(),
          body: JSON.stringify({
            space_key: extractSpace,
            max_pages: extractMaxPages,
          }),
        }
      );
      const data = await resp.json();
      setExtraction(data);
    } catch {
      setExtraction(null);
    }
    setExtracting(false);
  };

  return (
    <ModuleGuard module="confluence">
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-foreground">Confluence Source</h1>
        <p className="text-sm text-muted-foreground">
          Browse spaces, search pages, and extract content from Confluence.
        </p>
      </div>

      {/* Connection test */}
      <div className="rounded-xl border border-border bg-background p-5">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Plug className="h-5 w-5 text-muted-foreground" />
            <div>
              <p className="text-sm font-medium text-foreground">Connection</p>
              {connected === true && (
                <p className="text-xs text-green-600">Connected to {connUrl}</p>
              )}
              {connected === false && (
                <p className="text-xs text-red-500">Not connected — check env vars</p>
              )}
            </div>
          </div>
          <button
            onClick={testConnection}
            disabled={connLoading}
            className="flex items-center gap-1.5 rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground transition-colors hover:bg-primary/90 disabled:opacity-50"
          >
            {connLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plug className="h-4 w-4" />}
            Test Connection
          </button>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 rounded-lg bg-muted p-1 w-fit">
        {(["browse", "search", "extract"] as const).map((tab) => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            className={cn(
              "rounded-md px-4 py-1.5 text-sm font-medium capitalize transition-colors",
              activeTab === tab
                ? "bg-background text-foreground shadow-sm"
                : "text-muted-foreground hover:text-foreground"
            )}
          >
            {tab}
          </button>
        ))}
      </div>

      {/* Browse Tab */}
      {activeTab === "browse" && (
        <div className="grid grid-cols-3 gap-4">
          {/* Spaces column */}
          <div className="rounded-xl border border-border bg-background">
            <div className="flex items-center justify-between border-b border-border px-4 py-3">
              <h3 className="text-sm font-semibold text-foreground">Spaces</h3>
              <button
                onClick={loadSpaces}
                disabled={spacesLoading}
                className="rounded-md p-1 text-muted-foreground hover:bg-muted hover:text-muted-foreground"
              >
                <RefreshCw className={cn("h-3.5 w-3.5", spacesLoading && "animate-spin")} />
              </button>
            </div>
            <div className="max-h-[500px] overflow-y-auto">
              {spaces.length === 0 && !spacesLoading && (
                <p className="px-4 py-8 text-center text-xs text-muted-foreground">
                  Click refresh to load spaces
                </p>
              )}
              {spacesLoading && (
                <div className="flex items-center justify-center py-8">
                  <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
                </div>
              )}
              {spaces.map((s) => (
                <button
                  key={s.key}
                  onClick={() => browseSpace(s)}
                  className={cn(
                    "flex w-full items-center justify-between border-b border-border px-4 py-2.5 text-left text-sm transition-colors hover:bg-primary/5",
                    selectedSpace?.key === s.key && "bg-primary/5 text-primary"
                  )}
                >
                  <span className="truncate font-medium">{s.name}</span>
                  <ChevronRight className="h-3.5 w-3.5 shrink-0 text-muted-foreground/50" />
                </button>
              ))}
            </div>
          </div>

          {/* Pages column */}
          <div className="rounded-xl border border-border bg-background">
            <div className="border-b border-border px-4 py-3">
              <h3 className="text-sm font-semibold text-foreground">
                {selectedSpace ? `Pages in ${selectedSpace.name}` : "Pages"}
              </h3>
            </div>
            <div className="max-h-[500px] overflow-y-auto">
              {browseLoading && (
                <div className="flex items-center justify-center py-8">
                  <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
                </div>
              )}
              {!browseLoading && spacePages.length === 0 && (
                <p className="px-4 py-8 text-center text-xs text-muted-foreground">
                  Select a space to browse pages
                </p>
              )}
              {spacePages.map((p) => (
                <button
                  key={p.id}
                  onClick={() => loadPage(p.id)}
                  className={cn(
                    "flex w-full items-center gap-2 border-b border-border px-4 py-2.5 text-left text-sm transition-colors hover:bg-muted/50",
                    pageDetail?.id === p.id && "bg-primary/5 text-primary"
                  )}
                >
                  <FileText className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
                  <span className="truncate">{p.title}</span>
                </button>
              ))}
            </div>
          </div>

          {/* Page detail column */}
          <div className="rounded-xl border border-border bg-background">
            <div className="border-b border-border px-4 py-3">
              <h3 className="text-sm font-semibold text-foreground">Page Content</h3>
            </div>
            <div className="max-h-[500px] overflow-y-auto p-4">
              {pageLoading && (
                <div className="flex items-center justify-center py-8">
                  <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
                </div>
              )}
              {!pageLoading && !pageDetail && (
                <p className="py-8 text-center text-xs text-muted-foreground">
                  Select a page to preview
                </p>
              )}
              {pageDetail && (
                <div>
                  <h4 className="mb-1 text-base font-semibold text-foreground">
                    {pageDetail.title}
                  </h4>
                  <p className="mb-3 text-xs text-muted-foreground">
                    {pageDetail.space_name} &middot; v{pageDetail.version}
                    {pageDetail.url && (
                      <a
                        href={pageDetail.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="ml-2 inline-flex items-center gap-0.5 text-primary hover:underline"
                      >
                        Open <ExternalLink className="h-3 w-3" />
                      </a>
                    )}
                  </p>
                  <div className="prose prose-sm max-w-none whitespace-pre-wrap text-xs text-foreground">
                    {pageDetail.content.slice(0, 5000)}
                    {pageDetail.content.length > 5000 && (
                      <p className="mt-2 italic text-muted-foreground">
                        [Showing first 5000 chars of {pageDetail.content.length}]
                      </p>
                    )}
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Search Tab */}
      {activeTab === "search" && (
        <div className="space-y-4">
          <div className="flex gap-2">
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && doSearch()}
              placeholder="Search Confluence pages..."
              className="flex-1 rounded-lg border border-input px-3 py-2 text-sm focus:border-primary/50 focus:outline-none focus:ring-2 focus:ring-primary/10"
            />
            <button
              onClick={doSearch}
              disabled={searchLoading || !searchQuery.trim()}
              className="flex items-center gap-1.5 rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground transition-colors hover:bg-primary/90 disabled:opacity-50"
            >
              {searchLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Search className="h-4 w-4" />}
              Search
            </button>
          </div>
          <div className="rounded-xl border border-border bg-background">
            {searchResults.length === 0 && !searchLoading && (
              <p className="px-4 py-8 text-center text-sm text-muted-foreground">
                Search for Confluence pages by keyword
              </p>
            )}
            {searchResults.map((r) => (
              <div
                key={r.id}
                className="flex items-start gap-3 border-b border-border px-4 py-3 last:border-0"
              >
                <FileText className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" />
                <div className="min-w-0">
                  <p className="text-sm font-medium text-foreground">{r.title}</p>
                  {r.excerpt && (
                    <p className="mt-0.5 truncate text-xs text-muted-foreground">{r.excerpt}</p>
                  )}
                  <p className="mt-0.5 text-xs text-muted-foreground">
                    Space: {r.space_key} &middot; ID: {r.id}
                  </p>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Extract Tab */}
      {activeTab === "extract" && (
        <div className="space-y-4">
          <div className="rounded-xl border border-border bg-background p-5">
            <h3 className="mb-3 text-sm font-semibold text-foreground">Extract Pages from Space</h3>
            <div className="flex items-end gap-3">
              <div className="flex-1">
                <label className="mb-1 block text-xs font-medium text-muted-foreground">Space Key</label>
                <input
                  type="text"
                  value={extractSpace}
                  onChange={(e) => setExtractSpace(e.target.value.toUpperCase())}
                  placeholder="e.g. PROJ"
                  className="w-full rounded-lg border border-input px-3 py-2 text-sm focus:border-primary/50 focus:outline-none focus:ring-2 focus:ring-primary/10"
                />
              </div>
              <div className="w-32">
                <label className="mb-1 block text-xs font-medium text-muted-foreground">Max Pages</label>
                <input
                  type="number"
                  value={extractMaxPages}
                  onChange={(e) => setExtractMaxPages(Number(e.target.value))}
                  min={1}
                  max={100}
                  className="w-full rounded-lg border border-input px-3 py-2 text-sm focus:border-primary/50 focus:outline-none focus:ring-2 focus:ring-primary/10"
                />
              </div>
              <button
                onClick={doExtract}
                disabled={extracting || !extractSpace.trim()}
                className="flex items-center gap-1.5 rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground transition-colors hover:bg-primary/90 disabled:opacity-50"
              >
                {extracting ? <Loader2 className="h-4 w-4 animate-spin" /> : <Download className="h-4 w-4" />}
                Extract
              </button>
            </div>
          </div>

          {extraction && (
            <div className="rounded-xl border border-green-200 bg-green-50 p-5">
              <div className="mb-3 flex items-center gap-2">
                <Check className="h-5 w-5 text-green-600" />
                <h3 className="text-sm font-semibold text-green-800">
                  Extracted {extraction.pages_extracted} pages from {extraction.space_name || extraction.space_key}
                </h3>
              </div>
              <div className="space-y-1">
                {extraction.content.map((p) => (
                  <div key={p.page_id} className="flex items-center gap-2 text-xs text-green-700">
                    <FileText className="h-3 w-3" />
                    <span className="font-medium">{p.title}</span>
                    <span className="text-green-500">({p.content_md.length.toLocaleString()} chars)</span>
                  </div>
                ))}
              </div>
              <p className="mt-3 text-xs text-green-600">
                Run ID: {extraction.run_id}
              </p>
            </div>
          )}
        </div>
      )}
    </div>
    </ModuleGuard>
  );
}
