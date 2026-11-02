const clamp01 = (x) => Math.max(0, Math.min(1, x));
const scale = (value, low, high) => (value === null || value === undefined ? null : clamp01((value - low) / (high - low)));
const round1 = (value) => Math.round(value * 10) / 10;

// Weighted mean over the components that are available (null components are skipped).
function weighted(components) {
  let total = 0;
  let weightSum = 0;
  for (const [weight, value] of components) {
    if (value === null || value === undefined || Number.isNaN(value)) continue;
    total += weight * value;
    weightSum += weight;
  }
  return weightSum ? (total / weightSum) * 100 : null;
}

const add = (a, b) => (a === null || a === undefined || b === null || b === undefined ? null : a + b);
const avg = (a, b) => (a === null || a === undefined || b === null || b === undefined ? null : (a + b) / 2);
const inverse = (value) => (value === null ? null : 1 - value);

export function boxScore(stats, top = {}, tripleDoubles = 0) {
  const { home, away } = stats;
  const maxPoints = Math.max(top.home?.pts ?? 0, top.away?.pts ?? 0) || null;
  const star = maxPoints === null ? null : clamp01(scale(maxPoints, 25, 50) + (tripleDoubles > 0 ? 0.25 : 0));

  return weighted([
    [0.2, scale(add(home.points, away.points), 195, 260)],
    [0.15, scale(avg(home.fgp, away.fgp), 41, 53)],
    [0.12, scale(add(home.tpm, away.tpm), 16, 38)],
    [0.12, scale(add(home.assists, away.assists), 40, 68)],
    [0.1, scale(add(add(home.steals, away.steals), add(home.blocks, away.blocks)), 9, 24)],
    [0.21, star],
    [0.1, inverse(scale(add(home.turnovers, away.turnovers), 22, 38))],
  ]);
}

export function flowScore(flow) {
  if (!flow) return null;
  const clutch = avg(inverse(scale(flow.clutchMargin, 2, 14)), inverse(scale(flow.clutchMin, 0, 6)));
  return weighted([
    [0.3, inverse(scale(flow.finalMargin, 2, 20))],
    [0.25, clutch],
    [0.15, scale(flow.leadChanges, 2, 16)],
    [0.1, flow.overtimes > 0 ? 1 : 0],
    [0.1, scale(flow.comebackDeficit, 10, 22)],
    [0.1, scale(flow.wpTension, 0.15, 0.7)],
  ]);
}

// Raw buzz level for a game; turned into a season percentile by the caller.
export function buzzValue(buzz) {
  if (!buzz) return null;
  const comments = (buzz.live?.comments ?? 0) + (buzz.post?.comments ?? 0);
  return comments > 0 ? Math.log1p(comments) : null;
}

export function percentileRanker(values) {
  const sorted = values.filter((v) => v !== null).sort((a, b) => a - b);
  if (sorted.length < 20) return () => null;
  return (value) => {
    if (value === null) return null;
    let below = 0;
    while (below < sorted.length && sorted[below] < value) below += 1;
    return (below / (sorted.length - 1)) * 100;
  };
}

export function rewatchScore({ stats, top, tripleDoubles, flow }, buzzPercentile = null) {
  const box = boxScore(stats, top, tripleDoubles);
  const flowPart = flowScore(flow);
  const total = weighted([
    [0.35, box === null ? null : box / 100],
    [0.45, flowPart === null ? null : flowPart / 100],
    [0.2, buzzPercentile === null ? null : buzzPercentile / 100],
  ]);
  if (total === null) return null;
  return {
    score: round1(total),
    box: box === null ? null : round1(box),
    flow: flowPart === null ? null : round1(flowPart),
    buzz: buzzPercentile === null ? null : round1(buzzPercentile),
  };
}
