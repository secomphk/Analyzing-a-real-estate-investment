// Korean-friendly formatting helpers used across charts and cards.

const koInt = new Intl.NumberFormat("ko-KR");
const koCompact = new Intl.NumberFormat("ko-KR", { notation: "compact" });

export function formatInt(n: number | null | undefined): string {
  if (n == null || Number.isNaN(n)) return "—";
  return koInt.format(Math.round(n));
}

export function formatCompact(n: number | null | undefined): string {
  if (n == null || Number.isNaN(n)) return "—";
  return koCompact.format(n);
}

export function formatPct(value: number | null | undefined, digits = 1): string {
  if (value == null || Number.isNaN(value)) return "—";
  const sign = value > 0 ? "+" : "";
  return `${sign}${(value * 100).toFixed(digits)}%`;
}

export function formatKrwPerM2(value: number | null | undefined): string {
  if (value == null) return "—";
  if (value >= 10_000_000) return `${(value / 10_000_000).toFixed(1)}천만원/㎡`;
  if (value >= 1_000_000) return `${(value / 10_000).toFixed(0)}만원/㎡`;
  return `${formatInt(value)}원/㎡`;
}

export function formatDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  return iso.slice(0, 10);
}
