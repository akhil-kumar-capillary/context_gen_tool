"use client";

import { useState } from "react";
import { useConfigApisStore, type ConfigCluster } from "@/stores/config-apis-store";
import { ChevronDown, ChevronRight, ToggleLeft, ToggleRight } from "lucide-react";
import { cn } from "@/lib/utils";

// ── Doc type → entity type mapping (mirrors backend DOC_ENTITY_TYPES) ──

const DOC_ENTITY_TYPES: Record<string, string[]> = {
  "01_LOYALTY_MASTER": [
    "program", "tier", "strategy", "alternate_currency",
    "partner_program", "event_type", "loyalty_custom_field",
  ],
  "02_CAMPAIGN_REFERENCE": [
    "campaign", "campaign_config", "message",
    "sms_template", "email_template",
  ],
  "03_PROMOTION_RULES": [
    "loyalty_promotion", "cart_promotion", "coupon_series",
    "rewards_group", "promotion_custom_field",
  ],
  "04_AUDIENCE_SEGMENTS": [
    "audience", "target_group", "behavioral_event", "audience_filter",
  ],
  "05_CUSTOMIZATIONS": [
    "customer_ef", "txn_ef", "line_item_ef",
    "customer_label", "org_hierarchy_node", "org_behavioral_event",
  ],
};

const ENTITY_LABELS: Record<string, string> = {
  program: "Programs",
  tier: "Tiers",
  strategy: "Strategies",
  alternate_currency: "Alt. Currencies",
  partner_program: "Partner Programs",
  event_type: "Event Types",
  loyalty_custom_field: "Custom Fields",
  campaign: "Campaigns",
  campaign_config: "Campaign Configs",
  message: "Messages",
  sms_template: "SMS Templates",
  email_template: "Email Templates",
  loyalty_promotion: "Loyalty Promotions",
  cart_promotion: "Cart Promotions",
  coupon_series: "Coupon Series",
  rewards_group: "Rewards Groups",
  promotion_custom_field: "Promo Custom Fields",
  audience: "Audiences",
  target_group: "Target Groups",
  behavioral_event: "Behavioral Events",
  audience_filter: "Audience Filters",
  customer_ef: "Customer Ext. Fields",
  txn_ef: "Transaction Ext. Fields",
  line_item_ef: "Line-Item Ext. Fields",
  customer_label: "Customer Labels",
  org_hierarchy_node: "Org Hierarchy",
  org_behavioral_event: "Org Events",
};

interface InclusionPanelProps {
  docKey: string;
}

export function InclusionPanel({ docKey }: InclusionPanelProps) {
  const { clusters, inclusions, setInclusion, setAllInclusions } =
    useConfigApisStore();

  const entityTypes = DOC_ENTITY_TYPES[docKey] || [];
  const docInclusions = inclusions[docKey] || {};

  // Group clusters by entity_type
  const clustersByType: Record<string, ConfigCluster[]> = {};
  for (const et of entityTypes) {
    clustersByType[et] = (clusters || []).filter(
      (c) => c.entity_type === et
    );
  }

  if (!clusters || clusters.length === 0) {
    return (
      <div className="p-4 text-sm text-gray-500">
        No clusters available. Run analysis first.
      </div>
    );
  }

  return (
    <div className="space-y-1">
      {entityTypes.map((et) => {
        const etClusters = clustersByType[et] || [];
        if (etClusters.length === 0) return null;

        return (
          <EntityTypeSection
            key={et}
            docKey={docKey}
            entityType={et}
            clusters={etClusters}
            docInclusions={docInclusions}
            setInclusion={setInclusion}
            setAllInclusions={setAllInclusions}
          />
        );
      })}
    </div>
  );
}

interface EntityTypeSectionProps {
  docKey: string;
  entityType: string;
  clusters: ConfigCluster[];
  docInclusions: Record<string, boolean>;
  setInclusion: (docKey: string, path: string, value: boolean) => void;
  setAllInclusions: (docKey: string, paths: string[], value: boolean) => void;
}

function EntityTypeSection({
  docKey,
  entityType,
  clusters,
  docInclusions,
  setInclusion,
  setAllInclusions,
}: EntityTypeSectionProps) {
  const [expanded, setExpanded] = useState(true);
  const label = ENTITY_LABELS[entityType] || entityType;

  // Count total configs across all subtypes
  const totalCount = clusters.reduce((s, c) => s + c.count, 0);

  // Check if entity type itself is included (default true)
  const isTypeIncluded = docInclusions[entityType] !== false;

  // Collect all template paths for this entity type
  const allPaths: string[] = [entityType];
  for (const cluster of clusters) {
    const etKey = cluster.entity_subtype
      ? `${entityType}:${cluster.entity_subtype}`
      : entityType;
    allPaths.push(etKey);
    for (const tid of cluster.template_ids) {
      allPaths.push(`${etKey}.${tid}`);
    }
  }

  const handleSelectAll = (value: boolean) => {
    setAllInclusions(docKey, allPaths, value);
  };

  return (
    <div className="border border-gray-200 rounded-lg overflow-hidden">
      {/* Section header */}
      <div
        className="flex items-center justify-between px-3 py-2 bg-gray-50 cursor-pointer hover:bg-gray-100"
        onClick={() => setExpanded(!expanded)}
      >
        <div className="flex items-center gap-2">
          {expanded ? (
            <ChevronDown className="h-4 w-4 text-gray-400" />
          ) : (
            <ChevronRight className="h-4 w-4 text-gray-400" />
          )}
          <span className="text-sm font-medium text-gray-700">{label}</span>
          <span className="text-xs text-gray-400">({totalCount})</span>
        </div>

        <div className="flex items-center gap-2" onClick={(e) => e.stopPropagation()}>
          <button
            className="text-xs text-violet-600 hover:text-violet-800"
            onClick={() => handleSelectAll(true)}
          >
            All
          </button>
          <span className="text-xs text-gray-300">|</span>
          <button
            className="text-xs text-gray-500 hover:text-gray-700"
            onClick={() => handleSelectAll(false)}
          >
            None
          </button>
        </div>
      </div>

      {/* Cluster items */}
      {expanded && (
        <div className="divide-y divide-gray-100">
          {clusters.map((cluster) => {
            const etKey = cluster.entity_subtype
              ? `${entityType}:${cluster.entity_subtype}`
              : entityType;
            const isClusterIncluded = docInclusions[etKey] !== false;

            return (
              <div key={etKey} className="px-3 py-1.5">
                {/* Cluster header with toggle */}
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2 min-w-0">
                    <button
                      onClick={() => setInclusion(docKey, etKey, !isClusterIncluded)}
                      className="flex-shrink-0"
                    >
                      {isClusterIncluded ? (
                        <ToggleRight className="h-5 w-5 text-violet-600" />
                      ) : (
                        <ToggleLeft className="h-5 w-5 text-gray-300" />
                      )}
                    </button>
                    <span
                      className={cn(
                        "text-sm truncate",
                        isClusterIncluded ? "text-gray-700" : "text-gray-400"
                      )}
                    >
                      {cluster.entity_subtype || entityType}
                    </span>
                  </div>
                  <div className="flex items-center gap-2 flex-shrink-0">
                    <span className="text-xs text-gray-400">
                      {cluster.count} configs
                    </span>
                    <span className="text-xs text-violet-500">
                      {cluster.template_ids.length} templates
                    </span>
                  </div>
                </div>

                {/* Template items (indented) */}
                {isClusterIncluded && cluster.template_ids.length > 0 && (
                  <div className="ml-7 mt-1 space-y-0.5">
                    {cluster.template_ids.map((tid, idx) => {
                      const tmplKey = `${etKey}.${tid}`;
                      const isIncluded = docInclusions[tmplKey] !== false;
                      const tmpl = cluster.templates[idx] as Record<string, unknown> | undefined;
                      const tmplName = tmpl
                        ? String(
                            tmpl.name || tmpl.programName || tmpl.campaignName ||
                            tmpl.seriesName || tmpl.promotionName || tmpl.label ||
                            tid
                          ).slice(0, 60)
                        : tid;

                      return (
                        <div
                          key={tid}
                          className="flex items-center justify-between"
                        >
                          <div className="flex items-center gap-1.5">
                            <button
                              onClick={() => setInclusion(docKey, tmplKey, !isIncluded)}
                            >
                              {isIncluded ? (
                                <ToggleRight className="h-4 w-4 text-violet-500" />
                              ) : (
                                <ToggleLeft className="h-4 w-4 text-gray-300" />
                              )}
                            </button>
                            <span
                              className={cn(
                                "text-xs truncate max-w-[200px]",
                                isIncluded ? "text-gray-600" : "text-gray-300"
                              )}
                              title={tmplName}
                            >
                              {tmplName}
                            </span>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}

                {/* Cluster metadata */}
                {isClusterIncluded && cluster.naming_pattern && (
                  <div className="ml-7 mt-1">
                    <span className="text-xs text-gray-400">
                      Pattern: {cluster.naming_pattern}
                    </span>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
