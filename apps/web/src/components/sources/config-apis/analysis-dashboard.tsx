"use client";

import { useConfigApisStore } from "@/stores/config-apis-store";
import { cn } from "@/lib/utils";
import { BarChart3, Hash, Layers, Settings2 } from "lucide-react";

const ENTITY_LABELS: Record<string, string> = {
  program: "Programs",
  tier: "Tiers",
  strategy: "Strategies",
  alternate_currency: "Alt. Currencies",
  partner_program: "Partner Programs",
  event_type: "Event Types",
  loyalty_custom_field: "Loyalty CF",
  campaign: "Campaigns",
  campaign_config: "Campaign Configs",
  message: "Messages",
  sms_template: "SMS Templates",
  email_template: "Email Templates",
  loyalty_promotion: "Loyalty Promos",
  cart_promotion: "Cart Promos",
  coupon_series: "Coupon Series",
  rewards_group: "Rewards Groups",
  promotion_custom_field: "Promo CF",
  audience: "Audiences",
  target_group: "Target Groups",
  behavioral_event: "Behavioral Events",
  audience_filter: "Audience Filters",
  customer_ef: "Customer EF",
  txn_ef: "Transaction EF",
  line_item_ef: "Line-Item EF",
  customer_label: "Customer Labels",
  org_hierarchy_node: "Org Hierarchy",
  org_behavioral_event: "Org Events",
};

const BAR_COLORS = [
  "bg-violet-500",
  "bg-blue-500",
  "bg-emerald-500",
  "bg-amber-500",
  "bg-rose-500",
  "bg-cyan-500",
  "bg-purple-500",
  "bg-teal-500",
  "bg-orange-500",
  "bg-indigo-500",
];

export function AnalysisDashboard() {
  const { entityTypeCounts, clusters, counters } = useConfigApisStore();

  if (!entityTypeCounts || Object.keys(entityTypeCounts).length === 0) {
    return null;
  }

  const totalConfigs = Object.values(entityTypeCounts).reduce((s, c) => s + c, 0);
  const maxCount = Math.max(...Object.values(entityTypeCounts));

  // Sort entity types by count
  const sortedTypes = Object.entries(entityTypeCounts)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 15);

  // Structural features from counters
  const structural = (counters as Record<string, unknown>)?.structural as
    | Array<[string, number]>
    | undefined;

  return (
    <div className="rounded-xl border border-gray-200 bg-white overflow-hidden">
      <div className="px-4 py-3 border-b border-gray-200 bg-gray-50">
        <div className="flex items-center gap-2">
          <BarChart3 className="h-4 w-4 text-violet-500" />
          <h3 className="text-sm font-medium text-gray-700">
            Analysis Overview
          </h3>
          <span className="text-xs text-gray-400 ml-auto">
            {totalConfigs} total configs across {Object.keys(entityTypeCounts).length} types
          </span>
        </div>
      </div>

      <div className="p-4 grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Entity counts bar chart */}
        <div>
          <div className="flex items-center gap-1.5 mb-3">
            <Hash className="h-3.5 w-3.5 text-gray-400" />
            <span className="text-xs font-medium text-gray-600 uppercase tracking-wide">
              Entity Counts
            </span>
          </div>
          <div className="space-y-1.5">
            {sortedTypes.map(([et, count], i) => {
              const pct = Math.max(2, (count / maxCount) * 100);
              return (
                <div key={et} className="flex items-center gap-2">
                  <span className="text-xs text-gray-500 w-28 truncate text-right" title={et}>
                    {ENTITY_LABELS[et] || et}
                  </span>
                  <div className="flex-1 h-5 bg-gray-100 rounded overflow-hidden">
                    <div
                      className={cn(
                        "h-full rounded transition-all",
                        BAR_COLORS[i % BAR_COLORS.length]
                      )}
                      style={{ width: `${pct}%` }}
                    />
                  </div>
                  <span className="text-xs font-mono text-gray-600 w-8 text-right">
                    {count}
                  </span>
                </div>
              );
            })}
          </div>
        </div>

        {/* Cluster summary cards */}
        <div>
          <div className="flex items-center gap-1.5 mb-3">
            <Layers className="h-3.5 w-3.5 text-gray-400" />
            <span className="text-xs font-medium text-gray-600 uppercase tracking-wide">
              Clusters ({clusters?.length || 0})
            </span>
          </div>
          <div className="space-y-2 max-h-[300px] overflow-auto">
            {clusters?.slice(0, 10).map((cluster, i) => (
              <div
                key={`${cluster.entity_type}-${cluster.entity_subtype}-${i}`}
                className="flex items-center justify-between p-2 rounded-lg border border-gray-100 bg-gray-50"
              >
                <div className="min-w-0">
                  <div className="flex items-center gap-1.5">
                    <span className="text-xs font-medium text-gray-700 truncate">
                      {ENTITY_LABELS[cluster.entity_type] || cluster.entity_type}
                    </span>
                    {cluster.entity_subtype && (
                      <span className="text-[10px] px-1.5 py-0.5 rounded bg-violet-100 text-violet-600">
                        {cluster.entity_subtype}
                      </span>
                    )}
                  </div>
                  {cluster.naming_pattern && (
                    <span className="text-[10px] text-gray-400">
                      Pattern: {cluster.naming_pattern}
                    </span>
                  )}
                </div>
                <div className="flex items-center gap-3 text-[10px] text-gray-400 flex-shrink-0">
                  <span>{cluster.count} configs</span>
                  <span>{cluster.template_ids.length} templates</span>
                  <span>depth {cluster.avg_depth}</span>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Structural features */}
        {structural && structural.length > 0 && (
          <div className="lg:col-span-2">
            <div className="flex items-center gap-1.5 mb-3">
              <Settings2 className="h-3.5 w-3.5 text-gray-400" />
              <span className="text-xs font-medium text-gray-600 uppercase tracking-wide">
                Structural Features
              </span>
            </div>
            <div className="flex gap-4">
              {structural.map(([feature, count]) => (
                <div
                  key={feature}
                  className="flex items-center gap-2 px-3 py-2 rounded-lg bg-gray-50 border border-gray-100"
                >
                  <span className="text-xs text-gray-600">{feature}</span>
                  <span className="text-xs font-mono font-medium text-violet-600">
                    {count}
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
