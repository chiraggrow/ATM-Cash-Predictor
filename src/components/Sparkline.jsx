import React, { useMemo } from "react";

export default function Sparkline({
  values = [],
  width = 132,
  height = 38,
  tone = "neutral",
  filled = true,
  label,
}) {
  const points = useMemo(
    () => values.filter((value) => Number.isFinite(value)),
    [values],
  );

  if (points.length < 2) {
    return <span className="sparkline-empty" aria-hidden="true" />;
  }

  const minimum = Math.min(...points);
  const maximum = Math.max(...points);
  const range = maximum - minimum || 1;
  const coordinates = points.map((value, index) => {
    const x = (index / (points.length - 1)) * (width - 4) + 2;
    const y = height - 4 - ((value - minimum) / range) * (height - 8);
    return [x, y];
  });
  const line = coordinates.map(([x, y]) => `${x},${y}`).join(" ");
  const area = [
    `M ${coordinates[0][0]} ${height}`,
    ...coordinates.map(([x, y]) => `L ${x} ${y}`),
    `L ${coordinates[coordinates.length - 1][0]} ${height}`,
    "Z",
  ].join(" ");
  const gradientId = `spark-${tone}-${width}-${height}`;

  return (
    <svg
      className={`sparkline sparkline-${tone}`}
      viewBox={`0 0 ${width} ${height}`}
      role={label ? "img" : undefined}
      aria-label={label}
      aria-hidden={label ? undefined : "true"}
    >
      {filled && (
        <>
          <defs>
            <linearGradient id={gradientId} x1="0" x2="0" y1="0" y2="1">
              <stop offset="0%" stopColor="currentColor" stopOpacity="0.2" />
              <stop offset="100%" stopColor="currentColor" stopOpacity="0" />
            </linearGradient>
          </defs>
          <path d={area} fill={`url(#${gradientId})`} stroke="none" />
        </>
      )}
      <polyline points={line} fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
      <circle cx={coordinates[coordinates.length - 1][0]} cy={coordinates[coordinates.length - 1][1]} r="2.2" fill="currentColor" />
    </svg>
  );
}
