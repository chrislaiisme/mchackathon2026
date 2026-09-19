"use client";

import { useState } from "react";
import {
  Brain,
  ChevronDown,
  MessageSquareText,
  Search,
  Sparkles,
  TrendingDown,
  TrendingUp,
  Users,
  WandSparkles,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { enterpriseInsights, type SegmentKey } from "@/lib/mock/enterprise-insights";
import { cn } from "@/lib/utils";

type Opportunity = (typeof enterpriseInsights.opportunities)[number];

function IntelligenceHeader({ onAskMarket }: { onAskMarket: () => void }) {
  const { overview } = enterpriseInsights;

  return (
    <section className="border border-border bg-card p-5">
      <div className="flex flex-col gap-5 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <p className="text-xs uppercase tracking-[0.24em] text-primary">{overview.eyebrow}</p>
          <h1 className="mt-2 font-serif text-4xl leading-tight tracking-tight">{overview.title}</h1>
          <p className="mt-3 max-w-3xl text-sm leading-6 text-muted-foreground">{overview.description}</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Button type="button" variant="outline" size="sm">
            {overview.period}
            <ChevronDown className="size-4" />
          </Button>
          <Button type="button" variant="outline" size="sm">
            {overview.audience}
            <ChevronDown className="size-4" />
          </Button>
          <Button type="button" size="sm" onClick={onAskMarket}>
            <Sparkles className="size-4" />
            Ask Your Market
          </Button>
        </div>
      </div>
    </section>
  );
}

function MetricCard({ metric }: { metric: (typeof enterpriseInsights.metrics)[number] }) {
  return (
    <article className="border border-border bg-card p-5">
      <p className="text-xs uppercase tracking-[0.2em] text-muted-foreground">{metric.label}</p>
      <div className="mt-4 text-3xl font-semibold tracking-tight">{metric.value}</div>
      <p
        className={cn(
          "mt-2 text-sm",
          metric.tone === "positive" && "text-emerald-700",
          metric.tone === "intelligence" && "text-primary",
          metric.tone === "trend" && "text-primary",
        )}
      >
        {metric.note}
      </p>
    </article>
  );
}

function TrendMomentumMap() {
  const trends = enterpriseInsights.trendMap;

  return (
    <section className="border border-border bg-card p-5">
      <div className="mb-4 flex items-start justify-between gap-4">
        <div>
          <p className="text-xs uppercase tracking-[0.22em] text-muted-foreground">Trend Intelligence</p>
          <h2 className="mt-2 font-serif text-3xl leading-tight">Trend Momentum Map</h2>
        </div>
        <span className="border border-border px-2 py-1 text-xs text-muted-foreground">Growth / Momentum ↑</span>
      </div>
      <div className="relative h-[430px] overflow-hidden border border-border bg-background">
        <div className="absolute left-1/2 top-0 h-full w-px bg-border" />
        <div className="absolute left-0 top-1/2 h-px w-full bg-border" />
        <div className="absolute left-4 top-4 text-xs uppercase tracking-[0.18em] text-muted-foreground">Emerging</div>
        <div className="absolute right-4 top-4 text-xs uppercase tracking-[0.18em] text-muted-foreground">Trending</div>
        <div className="absolute bottom-9 left-4 text-xs uppercase tracking-[0.18em] text-muted-foreground">Niche</div>
        <div className="absolute bottom-9 right-4 text-xs uppercase tracking-[0.18em] text-muted-foreground">Mature</div>
        <div className="absolute bottom-3 right-4 text-xs uppercase tracking-[0.16em] text-muted-foreground">
          Current Popularity →
        </div>
        {trends.map((trend) => {
          const size = 36 + trend.score / 3;

          return (
            <div
              key={trend.name}
              className="group absolute -translate-x-1/2 -translate-y-1/2"
              style={{ left: `${trend.popularity}%`, top: `${100 - trend.growth}%` }}
            >
              <button
                type="button"
                className="rounded-full border border-primary/25 bg-primary/20 text-xs font-medium text-foreground shadow-sm transition hover:bg-primary/30"
                style={{ width: size, height: size }}
                aria-label={`${trend.name} trend details`}
              >
                {trend.name.split(" ")[0]}
              </button>
              <div className="pointer-events-none absolute left-1/2 top-full z-10 mt-2 w-56 -translate-x-1/2 border border-border bg-card p-3 text-left opacity-0 shadow-lg transition group-hover:opacity-100">
                <div className="font-serif text-lg">{trend.name}</div>
                <div className="mt-2 space-y-1 text-xs text-muted-foreground">
                  <p>Trend Score {trend.score}</p>
                  <p>{trend.momentum} momentum</p>
                  <p>{trend.volume} interactions</p>
                  <p>Strongest: {trend.audience}</p>
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
}

function TrendingNow() {
  return (
    <section className="border border-border bg-card p-5">
      <p className="text-xs uppercase tracking-[0.22em] text-muted-foreground">Trending Now</p>
      <div className="mt-5 space-y-3">
        {enterpriseInsights.trendingNow.map((trend) => {
          const isDown = trend.direction === "down";

          return (
            <article key={trend.name} className="border border-border p-4">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <h3 className="font-serif text-xl leading-tight">{trend.name}</h3>
                  <p className="mt-2 text-xs uppercase tracking-[0.16em] text-muted-foreground">{trend.status}</p>
                </div>
                <span className={cn("inline-flex items-center gap-1 text-sm font-medium", isDown ? "text-amber-700" : "text-emerald-700")}>
                  {isDown ? <TrendingDown className="size-4" /> : <TrendingUp className="size-4" />}
                  {trend.movement}
                </span>
              </div>
              <p className="mt-3 text-sm leading-6 text-muted-foreground">{trend.evidence}</p>
            </article>
          );
        })}
      </div>
    </section>
  );
}

function ColorPaletteCard() {
  return (
    <article className="border border-border bg-card p-5">
      <h3 className="text-xs uppercase tracking-[0.22em] text-muted-foreground">Colors</h3>
      <div className="mt-5 space-y-4">
        {enterpriseInsights.marketDna.colors.map((color) => (
          <div key={color.name} className="flex items-center gap-3">
            <span className="size-10 border border-border" style={{ backgroundColor: color.swatch }} />
            <div className="min-w-0 flex-1">
              <div className="text-sm font-medium">{color.name}</div>
              <div className="text-xs text-muted-foreground">{color.value}</div>
            </div>
          </div>
        ))}
      </div>
    </article>
  );
}

function MarketAttributeCard({
  title,
  items,
}: {
  title: string;
  items: { name: string; value: string; strength: number }[];
}) {
  return (
    <article className="border border-border bg-card p-5">
      <h3 className="text-xs uppercase tracking-[0.22em] text-muted-foreground">{title}</h3>
      <div className="mt-5 space-y-4">
        {items.map((item) => (
          <div key={item.name}>
            <div className="flex items-center justify-between gap-3">
              <span className="text-sm font-medium">{item.name}</span>
              <span className="text-xs text-muted-foreground">{item.value}</span>
            </div>
            <div className="mt-2 h-px bg-border">
              <div className="h-px bg-primary" style={{ width: `${item.strength}%` }} />
            </div>
          </div>
        ))}
      </div>
    </article>
  );
}

function MarketDNA() {
  const { marketDna } = enterpriseInsights;

  return (
    <section className="space-y-4">
      <div>
        <p className="text-xs uppercase tracking-[0.24em] text-primary">Market DNA</p>
        <h2 className="mt-2 font-serif text-3xl">What the market is made of right now</h2>
      </div>
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <ColorPaletteCard />
        <MarketAttributeCard title="Styles" items={marketDna.styles} />
        <MarketAttributeCard title="Silhouettes" items={marketDna.silhouettes} />
        <MarketAttributeCard title="Materials" items={marketDna.materials} />
      </div>
    </section>
  );
}

function AudienceInsights({ selectedSegment, onSelect }: { selectedSegment: SegmentKey; onSelect: (segment: SegmentKey) => void }) {
  const segments = enterpriseInsights.segments;
  const active = segments[selectedSegment];
  const segmentKeys = Object.keys(segments) as SegmentKey[];

  return (
    <section className="border border-border bg-card p-5">
      <div className="mb-5 flex items-center gap-2">
        <Users className="size-5 text-primary" />
        <h2 className="font-serif text-3xl">Audience Intelligence</h2>
      </div>
      <div className="flex flex-wrap gap-2">
        {segmentKeys.map((key) => (
          <Button key={key} type="button" size="sm" variant={selectedSegment === key ? "default" : "outline"} onClick={() => onSelect(key)}>
            {segments[key].label}
          </Button>
        ))}
      </div>
      <div className="mt-6">
        <p className="text-xs uppercase tracking-[0.22em] text-muted-foreground">{active.title}</p>
        <div className="mt-4 grid gap-3 sm:grid-cols-2">
          {[
            ["Top Trend", active.topTrend],
            ["Top Color", active.topColor],
            ["Top Silhouette", active.topSilhouette],
            ["Top Material", active.topMaterial],
            ["Try-on Affinity", active.tryOnAffinity],
          ].map(([label, value]) => (
            <div key={label} className="border border-border p-3">
              <div className="text-xs text-muted-foreground">{label}</div>
              <div className="mt-1 text-sm font-medium">{value}</div>
            </div>
          ))}
        </div>
        <p className="mt-5 border-l border-primary pl-4 text-sm leading-6 text-muted-foreground">{active.interpretation}</p>
      </div>
    </section>
  );
}

function SignalEvidence() {
  const icons = [MessageSquareText, Brain, Sparkles];

  return (
    <section className="border border-border bg-card p-5">
      <p className="text-xs uppercase tracking-[0.22em] text-muted-foreground">Signal Evidence</p>
      <h2 className="mt-2 font-serif text-3xl">Why this trend matters</h2>
      <div className="mt-5 space-y-3">
        {enterpriseInsights.evidence.map((signal, index) => {
          const Icon = icons[index] || MessageSquareText;

          return (
            <article key={signal.source} className="border border-border p-4">
              <div className="flex items-start gap-3">
                <Icon className="mt-1 size-4 text-primary" />
                <div>
                  <p className="text-xs uppercase tracking-[0.18em] text-muted-foreground">{signal.source}</p>
                  <p className="mt-2 font-medium">{signal.signal}</p>
                  <p className="mt-1 text-sm text-primary">{signal.movement}</p>
                  <p className="mt-2 text-sm leading-6 text-muted-foreground">{signal.detail}</p>
                </div>
              </div>
            </article>
          );
        })}
      </div>
    </section>
  );
}

function ProductOpportunityCard({ opportunity, onGenerate }: { opportunity: Opportunity; onGenerate: (opportunity: Opportunity) => void }) {
  return (
    <article className="flex flex-col border border-border bg-card p-5">
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="text-xs uppercase tracking-[0.22em] text-primary">Opportunity - {opportunity.type}</p>
          <h3 className="mt-2 font-serif text-2xl leading-tight">{opportunity.name}</h3>
        </div>
        <div className="text-right">
          <div className="text-xs text-muted-foreground">Trend Score</div>
          <div className="text-2xl font-semibold">{opportunity.score}</div>
        </div>
      </div>
      <div className="mt-5 flex flex-wrap gap-2">
        {opportunity.evidence.map((item) => (
          <span key={item} className="border border-border bg-background/50 px-2.5 py-1 text-xs text-muted-foreground">
            {item}
          </span>
        ))}
      </div>
      <div className="mt-5 space-y-4 text-sm leading-6 text-muted-foreground">
        <p>{opportunity.insight}</p>
        <p className="border-l border-primary pl-4 text-foreground">{opportunity.action}</p>
      </div>
      <div className="mt-6 flex flex-wrap gap-2">
        <Button type="button" variant="outline" size="sm">
          Explore Insight
        </Button>
        {opportunity.canGenerate && (
          <Button type="button" size="sm" onClick={() => onGenerate(opportunity)}>
            Generate Concept
            <WandSparkles className="size-4" />
          </Button>
        )}
      </div>
    </article>
  );
}

function ProductOpportunities({ onGenerate }: { onGenerate: (opportunity: Opportunity) => void }) {
  return (
    <section className="space-y-4">
      <div>
        <p className="text-xs uppercase tracking-[0.24em] text-primary">AI Product Opportunities</p>
        <h2 className="mt-2 font-serif text-3xl">From signal to business action</h2>
      </div>
      <div className="grid gap-4 lg:grid-cols-3">
        {enterpriseInsights.opportunities.map((opportunity) => (
          <ProductOpportunityCard key={opportunity.id} opportunity={opportunity} onGenerate={onGenerate} />
        ))}
      </div>
    </section>
  );
}

function GenerateConceptPlaceholder({ opportunity, onClose }: { opportunity: Opportunity | null; onClose: () => void }) {
  if (!opportunity) {
    return null;
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-foreground/30 p-4 backdrop-blur-sm">
      <section className="w-full max-w-lg border border-border bg-card p-6 shadow-xl">
        <div className="flex items-start justify-between gap-6">
          <div>
            <p className="text-xs uppercase tracking-[0.22em] text-primary">Generate Product Concept</p>
            <h2 className="mt-2 font-serif text-3xl">{opportunity.name}</h2>
          </div>
          <Button type="button" variant="ghost" size="sm" onClick={onClose}>
            Close
          </Button>
        </div>
        <div className="mt-6">
          <p className="text-xs uppercase tracking-[0.18em] text-muted-foreground">Based on</p>
          <div className="mt-3 flex flex-wrap gap-2">
            {opportunity.concept.map((item) => (
              <span key={item} className="border border-border px-3 py-2 text-sm">
                {item}
              </span>
            ))}
          </div>
        </div>
        <p className="mt-6 border-l border-primary pl-4 text-sm leading-6 text-muted-foreground">
          AI concept generation will be connected here. No external model is called in this prototype.
        </p>
      </section>
    </div>
  );
}

function AskMarketPanel({ open, onClose }: { open: boolean; onClose: () => void }) {
  if (!open) {
    return null;
  }

  return (
    <aside className="fixed right-4 top-20 z-50 w-[min(380px,calc(100vw-2rem))] border border-border bg-card p-5 shadow-xl">
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="text-xs uppercase tracking-[0.22em] text-primary">Ask Your Market</p>
          <h2 className="mt-2 font-serif text-2xl">Consumer intelligence query</h2>
        </div>
        <Button type="button" variant="ghost" size="sm" onClick={onClose}>
          Close
        </Button>
      </div>
      <div className="mt-5 flex items-center gap-2 border border-input bg-background px-3 py-2">
        <Search className="size-4 text-muted-foreground" />
        <input
          className="min-w-0 flex-1 bg-transparent text-sm outline-none"
          placeholder="Ask a question about your consumers..."
        />
      </div>
      <div className="mt-4 space-y-2">
        {enterpriseInsights.askMarket.suggestions.map((suggestion) => (
          <button key={suggestion} type="button" className="block w-full border border-border px-3 py-2 text-left text-sm text-muted-foreground">
            {suggestion}
          </button>
        ))}
      </div>
      <p className="mt-5 border-l border-primary pl-4 text-sm leading-6 text-muted-foreground">
        {enterpriseInsights.askMarket.response}
      </p>
    </aside>
  );
}

export function InsightsDashboard() {
  const [selectedSegment, setSelectedSegment] = useState<SegmentKey>("all");
  const [conceptOpportunity, setConceptOpportunity] = useState<Opportunity | null>(null);
  const [askMarketOpen, setAskMarketOpen] = useState(false);

  return (
    <div className="space-y-6">
      <IntelligenceHeader onAskMarket={() => setAskMarketOpen(true)} />

      <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        {enterpriseInsights.metrics.map((metric) => (
          <MetricCard key={metric.label} metric={metric} />
        ))}
      </section>

      <section className="grid gap-6 xl:grid-cols-[minmax(0,1.45fr)_minmax(320px,0.55fr)]">
        <TrendMomentumMap />
        <TrendingNow />
      </section>

      <MarketDNA />

      <section className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_420px]">
        <AudienceInsights selectedSegment={selectedSegment} onSelect={setSelectedSegment} />
        <SignalEvidence />
      </section>

      <ProductOpportunities onGenerate={setConceptOpportunity} />

      <GenerateConceptPlaceholder opportunity={conceptOpportunity} onClose={() => setConceptOpportunity(null)} />
      <AskMarketPanel open={askMarketOpen} onClose={() => setAskMarketOpen(false)} />
    </div>
  );
}
