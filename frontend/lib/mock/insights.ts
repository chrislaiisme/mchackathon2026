import type { KpiMetric, RankedSignal, TrendInsight, TrendPoint } from "@/lib/types";

export const kpis: KpiMetric[] = [
  { label: "Preference Signals", value: "284K", change: "+18.4% vs. last month", tone: "positive" },
  { label: "Recommendation Feedback", value: "71%", change: "positive affinity rate", tone: "positive" },
  { label: "KOL Signal Match", value: "63%", change: "+9 pts correlation", tone: "neutral" },
  { label: "At-Risk Styles", value: "4", change: "declining for 3 weeks", tone: "warning" },
];

export const trendMomentum: TrendPoint[] = [
  { label: "Apr", value: 42 },
  { label: "May", value: 49 },
  { label: "Jun", value: 54 },
  { label: "Jul", value: 66 },
  { label: "Aug", value: 74 },
  { label: "Sep", value: 83 },
];

export const emergingTrends: TrendInsight[] = [
  {
    name: "Soft Utility",
    momentum: 86,
    audience: "Gen Z / urban commuters",
    signal: "Cargo details are rising when softened by satin, drape, and muted purple-grey palettes.",
  },
  {
    name: "Quiet Lavender",
    momentum: 78,
    audience: "Young professionals",
    signal: "Lavender is moving from occasion wear into office knits and light outerwear.",
  },
  {
    name: "Romantic Minimalism",
    momentum: 69,
    audience: "Premium casual buyers",
    signal: "Consumers are saving bow, lace, and sheer details when grounded in simple silhouettes.",
  },
];

export const popularColors: RankedSignal[] = [
  { label: "Lavender Mist", value: 82, note: "+21% saves" },
  { label: "Warm Stone", value: 74, note: "+14% try-ons" },
  { label: "Ink Navy", value: 66, note: "stable" },
  { label: "Pale Sage", value: 61, note: "+8% comments" },
];

export const styleSignals: RankedSignal[] = [
  { label: "Minimal Tailoring", value: 79, note: "office-to-dinner" },
  { label: "Relaxed Street", value: 72, note: "weekend intent" },
  { label: "Soft Romantic", value: 58, note: "occasion-led" },
  { label: "Vintage Prep", value: 47, note: "losing speed" },
];

export const silhouettes: RankedSignal[] = [
  { label: "Column", value: 77, note: "strong in knitwear" },
  { label: "Relaxed Wide-Leg", value: 70, note: "high repeat interest" },
  { label: "Cropped Jacket", value: 64, note: "KOL-supported" },
  { label: "Bodycon Mini", value: 38, note: "-12% affinity" },
];

export const materials: RankedSignal[] = [
  { label: "Soft Knit", value: 81, note: "comfort signal" },
  { label: "Washed Satin", value: 73, note: "evening crossover" },
  { label: "Technical Cotton", value: 63, note: "utility adoption" },
  { label: "High Shine Vegan Leather", value: 41, note: "niche demand" },
];

export const segmentInsights = [
  {
    segment: "Gen Z Discovery",
    demand: "Soft utility sets",
    driver: "TikTok outfit saves and AI stylist refinement requests",
  },
  {
    segment: "Millennial Workwear",
    demand: "Lavender knits and relaxed blazers",
    driver: "Work event prompts with comfort constraints",
  },
  {
    segment: "Premium Casual",
    demand: "Minimal silhouettes with one romantic detail",
    driver: "High like-rate after visual comparison cards",
  },
];

export const kolSignals = [
  { creator: "Mina Cho", platform: "Instagram", signal: "lavender suiting", lift: 24 },
  { creator: "Eli Park", platform: "TikTok", signal: "soft cargo trousers", lift: 31 },
  { creator: "Noa Studio", platform: "YouTube", signal: "quiet capsule styling", lift: 17 },
];

export const businessInsights = [
  "Move lavender from seasonal capsules into core knitwear. Consumer preference and KOL signals are now reinforcing each other.",
  "Test soft utility as a styling story instead of a hard streetwear drop. Interest is strongest when cargo details are paired with drape.",
  "Reduce buys on bodycon mini silhouettes for the next cycle. Feedback is shifting toward column and relaxed wide-leg shapes.",
];
