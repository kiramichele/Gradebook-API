"use client";

import { useEffect, useState } from "react";

import { api } from "@/lib/api";
import { number, percent } from "@/lib/format";
import type { Assignment, AssignmentStats } from "@/lib/types";
import { useAsync } from "@/lib/useAsync";

import { ErrorMessage } from "./ErrorMessage";

type Props = {
  assignment: Assignment;
  /** Changes whenever grades change, so the stats refresh. */
  version: unknown;
  onClose: () => void;
};

export function StatsPanel({ assignment, version, onClose }: Props) {
  const [includeMissing, setIncludeMissing] = useState(false);
  const stats = useAsync(
    () => api.assignments.stats(assignment.id, includeMissing),
    [assignment.id, includeMissing, version],
  );

  useEffect(() => {
    const onKey = (event: globalThis.KeyboardEvent) => event.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const s = stats.data;
  return (
    <aside className="panel" aria-label={`Stats for ${assignment.title}`}>
      <div className="spread">
        <h2 style={{ margin: 0 }}>{assignment.title}</h2>
        <button type="button" onClick={onClose} aria-label="Close stats">
          Close
        </button>
      </div>
      <p className="muted" style={{ margin: "4px 0 0" }}>
        Out of {assignment.points_possible} points
      </p>
      <ErrorMessage error={stats.error} />
      {s && (
        <>
          <label className="checkbox" style={{ marginTop: 12 }}>
            <input
              type="checkbox"
              checked={includeMissing}
              onChange={(e) => setIncludeMissing(e.target.checked)}
            />
            Count missing work as 0
          </label>

          <div className="tiles" data-testid="stats-tiles">
            <Tile label="Mean" value={number(s.mean)} sub={percent(s.mean_percent)} />
            <Tile label="Median" value={number(s.median)} sub={percent(s.median_percent)} />
            <Tile label="Std dev" value={number(s.std_dev)} />
            <Tile label="Low" value={number(s.min)} />
            <Tile label="High" value={number(s.max)} />
            <Tile label="Scores" value={String(s.count)} />
          </div>

          <p className="muted" style={{ fontSize: "0.85rem" }}>
            {s.enrolled} enrolled · {s.graded} graded · {s.missing} missing · {s.excused} excused ·{" "}
            {s.ungraded} not graded yet
          </p>

          <h3>Distribution</h3>
          {s.count ? <Histogram stats={s} /> : <p className="muted">No scores yet.</p>}

          <h3>Letter grades</h3>
          <table className="plain">
            <tbody>
              {Object.entries(s.letters)
                .filter(([, count]) => count > 0)
                .map(([letter, count]) => (
                  <tr key={letter}>
                    <td>{letter}</td>
                    <td className="num">{count}</td>
                  </tr>
                ))}
            </tbody>
          </table>
        </>
      )}
    </aside>
  );
}

function Tile({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="tile">
      <div className="label">{label}</div>
      <div className="value">{value}</div>
      {sub && <div className="label">{sub}</div>}
    </div>
  );
}

function binLabel(lower: number, upper: number | null): string {
  return upper === null ? `over ${lower}%` : `${lower}–${upper}%`;
}

/** One series of counts by percent bin. Only the tallest bar is labeled; hover or focus shows any. */
function Histogram({ stats }: { stats: AssignmentStats }) {
  const [hovered, setHovered] = useState<number | null>(null);
  const bins = stats.histogram;
  const max = Math.max(...bins.map((b) => b.count));
  const tallest = bins.findIndex((b) => b.count === max);
  const [showTable, setShowTable] = useState(false);

  return (
    <figure className="histogram" style={{ margin: 0 }}>
      <div className="histogram-plot" role="list" aria-label="Score distribution">
        {bins.map((bin, i) => {
          const label = `${binLabel(bin.lower, bin.upper)}: ${bin.count} student${bin.count === 1 ? "" : "s"}`;
          return (
            <div
              key={`${bin.lower}-${bin.upper}`}
              className="histogram-slot"
              role="listitem"
              tabIndex={0}
              aria-label={label}
              onMouseEnter={() => setHovered(i)}
              onMouseLeave={() => setHovered(null)}
              onFocus={() => setHovered(i)}
              onBlur={() => setHovered(null)}
            >
              {hovered === i && <span className="tooltip">{label}</span>}
              {i === tallest && max > 0 && <span className="histogram-label">{bin.count}</span>}
              {bin.count > 0 && (
                <div className="histogram-bar" style={{ height: `${(bin.count / max) * 85}%` }} />
              )}
            </div>
          );
        })}
      </div>
      <div className="histogram-axis" aria-hidden="true">
        {bins.map((bin) => (
          <span key={`${bin.lower}-${bin.upper}`}>{bin.upper === null ? ">100" : bin.lower}</span>
        ))}
      </div>
      <figcaption className="muted" style={{ fontSize: "0.8rem", marginTop: 4 }}>
        Students per score range (% of points possible).{" "}
        <button type="button" className="link" onClick={() => setShowTable(!showTable)}>
          {showTable ? "Hide table" : "Show as table"}
        </button>
      </figcaption>
      {showTable && (
        <table className="plain" style={{ marginTop: 8 }}>
          <thead>
            <tr>
              <th>Range</th>
              <th className="num">Students</th>
            </tr>
          </thead>
          <tbody>
            {bins.map((bin) => (
              <tr key={`${bin.lower}-${bin.upper}`}>
                <td>{binLabel(bin.lower, bin.upper)}</td>
                <td className="num">{bin.count}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </figure>
  );
}
