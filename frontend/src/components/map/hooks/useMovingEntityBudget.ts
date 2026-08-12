import { useCallback, useEffect, useMemo, useState } from 'react';

const DEFAULT_BUDGET = 16_000;
const MIN_BUDGET = 1_000;
const MAX_BUDGET = 250_000;

const PROFILE_CAPS: Record<string, number> = {
  low: 8_000,
  balanced: 16_000,
  performance: 40_000,
  maximum: MAX_BUDGET,
};

type RuntimeBudgetPrefs = {
  map_marker_budget?: number;
  profile?: string;
};

function effectiveBudget(value: RuntimeBudgetPrefs | undefined): number {
  const requested = Number(value?.map_marker_budget);
  const normalized = Number.isFinite(requested)
    ? Math.max(MIN_BUDGET, Math.min(MAX_BUDGET, Math.trunc(requested)))
    : DEFAULT_BUDGET;
  const cap = PROFILE_CAPS[String(value?.profile || 'balanced')] ?? PROFILE_CAPS.balanced;
  return Math.min(normalized, cap);
}

export function useMovingEntityBudget(enabledLayerCount: number) {
  const [budget, setBudget] = useState(DEFAULT_BUDGET);

  useEffect(() => {
    let cancelled = false;
    const apply = (value: RuntimeBudgetPrefs | undefined) => {
      if (!cancelled) setBudget(effectiveBudget(value));
    };
    fetch('/api/intelligence/settings/runtime', { cache: 'no-store' })
      .then((response) => (response.ok ? response.json() : null))
      .then((value) => apply(value || undefined))
      .catch(() => {});
    const onPreferences = (event: Event) => {
      apply((event as CustomEvent<RuntimeBudgetPrefs>).detail);
    };
    window.addEventListener('sb-runtime-prefs-updated', onPreferences);
    return () => {
      cancelled = true;
      window.removeEventListener('sb-runtime-prefs-updated', onPreferences);
    };
  }, []);

  const perLayerBudget = useMemo(
    () => Math.max(250, Math.floor(budget / Math.max(1, enabledLayerCount))),
    [budget, enabledLayerCount],
  );
  const limit = useCallback(
    <T,>(items: T[] | undefined): T[] | undefined =>
      items && items.length > perLayerBudget ? items.slice(0, perLayerBudget) : items,
    [perLayerBudget],
  );
  return { totalBudget: budget, perLayerBudget, limit };
}
