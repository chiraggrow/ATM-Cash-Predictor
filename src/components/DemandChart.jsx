import React, { useMemo, useState } from "react";
import { formatChartDate, formatCompact, formatNumber } from "../format.js";

const WIDTH = 920;
const HEIGHT = 320;
const PADDING = { top: 18, right: 18, bottom: 34, left: 62 };
const PLOT_WIDTH = WIDTH - PADDING.left - PADDING.right;
const PLOT_HEIGHT = HEIGHT - PADDING.top - PADDING.bottom;

function niceMaximum(value) {
  if (!Number.isFinite(value) || value <= 0) return 1;
  const exponent = 10 ** Math.floor(Math.log10(value));
  const ratio = value / exponent;
  const nice = ratio <= 1 ? 1 : ratio <= 2 ? 2 : ratio <= 2.5 ? 2.5 : ratio <= 5 ? 5 : 10;
  return nice * exponent;
}

function buildSequence(points, nextForecast, cumulative) {
  const rows = (points || [])
    .map((point) => ({
      date: point.date,
      observed: Number.isFinite(point.observed) ? point.observed : null,
      prediction: Number.isFinite(point.prediction) ? point.prediction : null,
    }))
    .filter((point) => point.observed !== null || point.prediction !== null);

  let sequence;
  let forecastPoint = null;
  if (cumulative) {
    let observedTotal = 0;
    let predictionTotal = 0;
    let predictionStarted = false;
    sequence = rows.map((row) => {
      if (row.observed !== null) observedTotal += row.observed;
      let cumulativePrediction = null;
      if (row.prediction !== null) {
        if (!predictionStarted) {
          predictionTotal = observedTotal - (row.observed ?? 0) + row.prediction;
          predictionStarted = true;
        } else {
          predictionTotal += row.prediction;
        }
        cumulativePrediction = predictionTotal;
      }
      return {
        date: row.date,
        observed: row.observed === null ? null : observedTotal,
        prediction: cumulativePrediction,
      };
    });
    if (nextForecast && sequence.length) {
      forecastPoint = {
        date: nextForecast.forecast_date,
        value: observedTotal + nextForecast.predicted_demand,
      };
    }
  } else {
    sequence = rows.map((row) => ({ ...row }));
    if (nextForecast) {
      forecastPoint = {
        date: nextForecast.forecast_date,
        value: nextForecast.predicted_demand,
      };
    }
  }

  return { sequence, forecastPoint };
}

export default function DemandChart({ points = [], nextForecast = null, cumulative = false }) {
  const [hoverIndex, setHoverIndex] = useState(null);
  const { sequence, forecastPoint } = useMemo(
    () => buildSequence(points, nextForecast, cumulative),
    [points, nextForecast, cumulative],
  );

  const total = sequence.length + (forecastPoint ? 1 : 0);
  const values = [
    ...sequence.flatMap((row) => [row.observed, row.prediction]).filter(Number.isFinite),
    ...(forecastPoint ? [forecastPoint.value] : []),
  ];
  const yMax = niceMaximum(Math.max(...values, 0) * 1.04);
  const xAt = (index) => PADDING.left + (total <= 1 ? PLOT_WIDTH / 2 : (index / (total - 1)) * PLOT_WIDTH);
  const yAt = (value) => PADDING.top + PLOT_HEIGHT - (value / yMax) * PLOT_HEIGHT;

  function lineSegments(getValue) {
    const segments = [];
    let current = [];
    sequence.forEach((row, index) => {
      const value = getValue(row);
      if (value === null || !Number.isFinite(value)) {
        if (current.length) segments.push(current);
        current = [];
        return;
      }
      current.push(`${xAt(index)},${yAt(value)}`);
    });
    if (current.length) segments.push(current);
    return segments;
  }

  const observedSegments = lineSegments((row) => row.observed);
  const predictionSegments = lineSegments((row) => row.prediction);

  const areaPath = useMemo(() => {
    const observed = sequence
      .map((row, index) => (row.observed === null ? null : [xAt(index), yAt(row.observed)]))
      .filter(Boolean);
    if (observed.length < 2) return "";
    return [
      `M ${observed[0][0]} ${PADDING.top + PLOT_HEIGHT}`,
      ...observed.map(([x, y]) => `L ${x} ${y}`),
      `L ${observed[observed.length - 1][0]} ${PADDING.top + PLOT_HEIGHT}`,
      "Z",
    ].join(" ");
  }, [sequence, yMax]);

  const xTickIndices = useMemo(() => {
    if (total <= 1) return [0];
    const desired = WIDTH < 700 ? 4 : 6;
    const step = Math.max(1, Math.ceil((total - 1) / desired));
    const indices = [];
    for (let index = 0; index < total; index += step) indices.push(index);
    if (indices[indices.length - 1] !== total - 1) indices.push(total - 1);
    return indices;
  }, [total]);

  const yearSpan = sequence.length > 1
    ? new Date(sequence[sequence.length - 1].date).getFullYear() - new Date(sequence[0].date).getFullYear()
    : 0;

  function hover(event) {
    if (total <= 1) {
      setHoverIndex(0);
      return;
    }
    const rect = event.currentTarget.getBoundingClientRect();
    const x = ((event.clientX - rect.left) / rect.width) * WIDTH;
    const raw = Math.round(((x - PADDING.left) / PLOT_WIDTH) * (total - 1));
    setHoverIndex(Math.max(0, Math.min(total - 1, raw)));
  }

  if (!sequence.length) {
    return (
      <div className="chart-empty">
        <span>No daily demand records are available for this window.</span>
      </div>
    );
  }

  const hoveredRow = hoverIndex !== null && hoverIndex < sequence.length ? sequence[hoverIndex] : null;
  const hoveredForecast = hoverIndex !== null && hoverIndex === sequence.length ? forecastPoint : null;
  const tooltipX = hoverIndex === null ? 0 : xAt(hoverIndex);
  const tooltipAlignment = tooltipX < WIDTH * 0.22
    ? "is-start"
    : tooltipX > WIDTH * 0.78
      ? "is-end"
      : "";

  return (
    <div className="chart-wrap">
      <span className="chart-axis-label">{cumulative ? "Cumulative cash units" : "Cash units"}</span>
      <svg
        className="demand-chart"
        viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
        role="img"
        aria-label={`${cumulative ? "Cumulative" : "Daily"} observed cash demand chart with model predictions`}
        onPointerMove={hover}
        onPointerLeave={() => setHoverIndex(null)}
      >
        <defs>
          <linearGradient id="demand-area" x1="0" x2="0" y1="0" y2="1">
            <stop offset="0%" stopColor="#647da8" stopOpacity="0.18" />
            <stop offset="100%" stopColor="#647da8" stopOpacity="0" />
          </linearGradient>
        </defs>

        {[0, 0.25, 0.5, 0.75, 1].map((ratio) => {
          const y = PADDING.top + PLOT_HEIGHT - ratio * PLOT_HEIGHT;
          return (
            <g key={ratio}>
              <line
                x1={PADDING.left}
                x2={WIDTH - PADDING.right}
                y1={y}
                y2={y}
                className="chart-grid"
              />
              <text x={PADDING.left - 10} y={y + 4} textAnchor="end" className="chart-tick">
                {formatCompact(yMax * ratio)}
              </text>
            </g>
          );
        })}

        {areaPath && <path d={areaPath} fill="url(#demand-area)" />}

        {observedSegments.map((segment, index) => (
          <polyline key={`observed-${index}`} points={segment.join(" ")} className="chart-line-observed" />
        ))}
        {predictionSegments.map((segment, index) => (
          <polyline key={`prediction-${index}`} points={segment.join(" ")} className="chart-line-prediction" />
        ))}

        {forecastPoint && (
          <g className="chart-forecast">
            <line
              x1={xAt(sequence.length)}
              x2={xAt(sequence.length)}
              y1={PADDING.top}
              y2={PADDING.top + PLOT_HEIGHT}
              className="chart-forecast-guide"
            />
            <circle cx={xAt(sequence.length)} cy={yAt(forecastPoint.value)} r="4.5" />
          </g>
        )}

        {xTickIndices.map((index) => {
          const date = index === sequence.length ? forecastPoint?.date : sequence[index]?.date;
          if (!date) return null;
          return (
            <text
              key={`x-${index}`}
              x={xAt(index)}
              y={HEIGHT - 8}
              textAnchor={index === 0 ? "start" : index === total - 1 ? "end" : "middle"}
              className="chart-tick"
            >
              {formatChartDate(date, { withYear: yearSpan > 0 })}
            </text>
          );
        })}

        {hoverIndex !== null && (
          <g className="chart-hover">
            <line
              x1={xAt(hoverIndex)}
              x2={xAt(hoverIndex)}
              y1={PADDING.top}
              y2={PADDING.top + PLOT_HEIGHT}
            />
            {hoveredRow?.observed !== null && hoveredRow?.observed !== undefined && (
              <circle cx={xAt(hoverIndex)} cy={yAt(hoveredRow.observed)} r="4" className="is-observed" />
            )}
            {hoveredRow?.prediction !== null && hoveredRow?.prediction !== undefined && (
              <circle cx={xAt(hoverIndex)} cy={yAt(hoveredRow.prediction)} r="4" className="is-prediction" />
            )}
            {hoveredForecast && (
              <circle cx={xAt(hoverIndex)} cy={yAt(hoveredForecast.value)} r="5" className="is-forecast" />
            )}
          </g>
        )}
      </svg>

      {hoverIndex !== null && (
        <div
          className={`chart-tooltip ${tooltipAlignment}`}
          style={{ left: `${(tooltipX / WIDTH) * 100}%` }}
          role="status"
        >
          <strong>{formatChartDate(hoveredForecast?.date || hoveredRow?.date, { withYear: true })}</strong>
          {hoveredForecast ? (
            <span>
              <i className="tooltip-swatch is-forecast" />
              Next-day estimate
              <b>{formatNumber(hoveredForecast.value)}</b>
            </span>
          ) : (
            <>
              <span>
                <i className="tooltip-swatch is-observed" />
                Observed
                <b>{formatNumber(hoveredRow.observed)}</b>
              </span>
              <span>
                <i className="tooltip-swatch is-prediction" />
                Model prediction
                <b>{hoveredRow.prediction === null || hoveredRow.prediction === undefined ? "—" : formatNumber(hoveredRow.prediction)}</b>
              </span>
            </>
          )}
          <small>{cumulative ? "Cumulative cash units" : "Cash units"}</small>
        </div>
      )}
    </div>
  );
}

export function ChartLegend({ showPrediction = true, showForecast = true }) {
  return (
    <div className="chart-legend">
      <span><i className="legend-line is-observed" />Observed</span>
      {showPrediction && <span><i className="legend-line is-prediction" />Model prediction</span>}
      {showForecast && <span><i className="legend-dot is-forecast" />Next-day estimate</span>}
    </div>
  );
}
