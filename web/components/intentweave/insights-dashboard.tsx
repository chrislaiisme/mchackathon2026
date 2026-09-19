import { AlertTriangle, Brain, LineChart, Megaphone, TrendingUp, Users } from "lucide-react";
import {
  businessInsights,
  emergingTrends,
  kpis,
  kolSignals,
  materials,
  popularColors,
  segmentInsights,
  silhouettes,
  styleSignals,
  trendMomentum,
} from "@/lib/mock/insights";
import type { RankedSignal } from "@/lib/types";
import { cn } from "@/lib/utils";

function KpiCard({ label, value, change, tone }: (typeof kpis)[number]) {
  return (
    <div className="rounded-lg border border-border bg-card p-5 shadow-sm">
      <div className="text-sm text-muted-foreground">{label}</div>
      <div className="mt-3 text-3xl font-semibold tracking-tight">{value}</div>
      <div
        className={cn(
          "mt-2 text-sm font-medium",
          tone === "positive" && "text-emerald-600",
          tone === "neutral" && "text-primary",
          tone === "warning" && "text-amber-600",
        )}
      >
        {change}
      </div>
    </div>
  );
}

function MomentumChart() {
  const max = Math.max(...trendMomentum.map((point) => point.value));

  return (
    <div className="rounded-lg border border-border bg-card p-5 shadow-sm">
      <div className="mb-5 flex items-center justify-between">
        <div>
          <h2 className="text-base font-semibold">Trend Momentum</h2>
          <p className="text-sm text-muted-foreground">Aggregated consumer and KOL signal velocity</p>
        </div>
        <LineChart className="size-5 text-primary" />
      </div>
      <div className="flex h-64 items-end gap-3">
        {trendMomentum.map((point) => (
          <div key={point.label} className="flex flex-1 flex-col items-center gap-2">
            <div className="flex w-full items-end rounded-md bg-muted" style={{ height: 210 }}>
              <div
                className="w-full rounded-md bg-primary"
                style={{ height: `${(point.value / max) * 100}%` }}
                title={`${point.label}: ${point.value}`}
              />
            </div>
            <span className="text-xs text-muted-foreground">{point.label}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function RankedList({ title, items }: { title: string; items: RankedSignal[] }) {
  return (
    <div className="rounded-lg border border-border bg-card p-5 shadow-sm">
      <h2 className="text-base font-semibold">{title}</h2>
      <div className="mt-4 space-y-4">
        {items.map((item) => (
          <div key={item.label} className="space-y-2">
            <div className="flex items-center justify-between gap-3 text-sm">
              <span className="font-medium">{item.label}</span>
              <span className="text-muted-foreground">{item.note}</span>
            </div>
            <div className="h-2 rounded-full bg-muted">
              <div className="h-2 rounded-full bg-primary" style={{ width: `${item.value}%` }} />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

export function InsightsDashboard() {
  return (
    <div className="space-y-6">
      <section className="rounded-lg border border-border bg-card p-6 shadow-sm">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <p className="text-xs font-medium uppercase tracking-[0.2em] text-primary">Enterprise Fashion Insights</p>
            <h1 className="mt-2 text-3xl font-semibold tracking-tight">Preference intelligence for fashion teams</h1>
            <p className="mt-3 max-w-3xl text-sm leading-6 text-muted-foreground">
              Mock dashboard showing how conversational styling signals, recommendation feedback, and KOL momentum
              become actionable merchandising intelligence.
            </p>
          </div>
          <div className="rounded-lg bg-accent px-4 py-3 text-sm font-medium text-accent-foreground">
            Market pulse: Sep 2026
          </div>
        </div>
      </section>

      <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        {kpis.map((metric) => (
          <KpiCard key={metric.label} {...metric} />
        ))}
      </section>

      <section className="grid gap-6 xl:grid-cols-[minmax(0,1.35fr)_minmax(360px,0.65fr)]">
        <MomentumChart />
        <div className="rounded-lg border border-border bg-card p-5 shadow-sm">
          <div className="mb-5 flex items-center gap-2">
            <TrendingUp className="size-5 text-primary" />
            <h2 className="text-base font-semibold">Emerging Trends</h2>
          </div>
          <div className="space-y-4">
            {emergingTrends.map((trend) => (
              <div key={trend.name} className="rounded-lg border border-border p-4">
                <div className="flex items-start justify-between gap-4">
                  <div>
                    <h3 className="text-sm font-semibold">{trend.name}</h3>
                    <p className="mt-1 text-xs text-muted-foreground">{trend.audience}</p>
                  </div>
                  <span className="rounded-md bg-primary px-2 py-1 text-xs font-medium text-primary-foreground">
                    {trend.momentum}
                  </span>
                </div>
                <p className="mt-3 text-sm leading-6 text-muted-foreground">{trend.signal}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <RankedList title="Popular Colors" items={popularColors} />
        <RankedList title="Popular Styles" items={styleSignals} />
        <RankedList title="Silhouettes" items={silhouettes} />
        <RankedList title="Materials" items={materials} />
      </section>

      <section className="grid gap-6 xl:grid-cols-3">
        <div className="rounded-lg border border-border bg-card p-5 shadow-sm xl:col-span-2">
          <div className="mb-5 flex items-center gap-2">
            <Users className="size-5 text-primary" />
            <h2 className="text-base font-semibold">Consumer Segment Insights</h2>
          </div>
          <div className="grid gap-4 md:grid-cols-3">
            {segmentInsights.map((segment) => (
              <div key={segment.segment} className="rounded-lg border border-border p-4">
                <h3 className="text-sm font-semibold">{segment.segment}</h3>
                <p className="mt-3 text-sm font-medium text-primary">{segment.demand}</p>
                <p className="mt-2 text-sm leading-6 text-muted-foreground">{segment.driver}</p>
              </div>
            ))}
          </div>
        </div>

        <div className="rounded-lg border border-border bg-card p-5 shadow-sm">
          <div className="mb-5 flex items-center gap-2">
            <Megaphone className="size-5 text-primary" />
            <h2 className="text-base font-semibold">KOL Signals</h2>
          </div>
          <div className="space-y-3">
            {kolSignals.map((signal) => (
              <div key={signal.creator} className="flex items-center justify-between rounded-lg border border-border p-3">
                <div>
                  <div className="text-sm font-semibold">{signal.creator}</div>
                  <div className="text-xs text-muted-foreground">
                    {signal.platform} - {signal.signal}
                  </div>
                </div>
                <div className="text-sm font-semibold text-emerald-600">+{signal.lift}%</div>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_360px]">
        <div className="rounded-lg border border-border bg-card p-5 shadow-sm">
          <div className="mb-5 flex items-center gap-2">
            <Brain className="size-5 text-primary" />
            <h2 className="text-base font-semibold">AI-Generated Business Insights</h2>
          </div>
          <div className="space-y-3">
            {businessInsights.map((insight) => (
              <div key={insight} className="rounded-lg bg-accent/60 p-4 text-sm leading-6 text-accent-foreground">
                {insight}
              </div>
            ))}
          </div>
        </div>

        <div className="rounded-lg border border-amber-200 bg-amber-50 p-5 text-amber-950 shadow-sm">
          <div className="mb-3 flex items-center gap-2">
            <AlertTriangle className="size-5" />
            <h2 className="text-base font-semibold">Next Watchlist</h2>
          </div>
          <p className="text-sm leading-6">
            Vintage prep is still visible in creator content but consumer feedback is flattening. Treat it as styling
            support, not a major buy direction.
          </p>
        </div>
      </section>
    </div>
  );
}
