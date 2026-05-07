type ClassValue = string | number | null | undefined | false;

/** Tiny ``classnames`` shim. Filters falsy values, joins with spaces.
 *  Skip a CSS-in-JS dep — class strings stay greppable. */
export function cn(...values: ClassValue[]): string {
  return values.filter(Boolean).join(" ");
}

/** ``cn`` variant that accepts a `Record<string, boolean>` for conditional classes. */
export function cx(
  base: ClassValue,
  conditions: Record<string, boolean | undefined>,
): string {
  const extras = Object.entries(conditions)
    .filter(([, v]) => Boolean(v))
    .map(([k]) => k);
  return cn(base, ...extras);
}
