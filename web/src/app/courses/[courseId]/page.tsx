"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { RequireAuth } from "@/components/AuthProvider";
import { ErrorMessage } from "@/components/ErrorMessage";
import { GradeGrid } from "@/components/GradeGrid";
import { RosterPanel } from "@/components/RosterPanel";
import { SetupPanel } from "@/components/SetupPanel";
import { StatsPanel } from "@/components/StatsPanel";
import { api } from "@/lib/api";
import type { Assignment } from "@/lib/types";
import { useAsync } from "@/lib/useAsync";

const TABS = ["Gradebook", "Roster", "Setup"] as const;
type Tab = (typeof TABS)[number];

export default function CoursePage() {
  return (
    <RequireAuth>
      <Course />
    </RequireAuth>
  );
}

function Course() {
  const { courseId } = useParams<{ courseId: string }>();
  const book = useAsync(() => api.courses.gradebook(courseId), [courseId]);
  const [tab, setTab] = useState<Tab | null>(null);
  const [statsFor, setStatsFor] = useState<Assignment | null>(null);
  const [exportError, setExportError] = useState<Error>();
  const closeStats = useCallback(() => setStatsFor(null), []);

  // Pick the starting tab once, from the first load: new courses open on
  // Setup. Deriving it on every render would yank the teacher to Gradebook
  // the moment they add their first category.
  const loaded = book.data !== undefined;
  const hasCategories = (book.data?.categories.length ?? 0) > 0;
  useEffect(() => {
    if (loaded) setTab((t) => t ?? (hasCategories ? "Gradebook" : "Setup"));
  }, [loaded, hasCategories]);

  if (book.error && !book.data) {
    return (
      <div className="page">
        <ErrorMessage error={book.error} />
        <Link href="/">Back to courses</Link>
      </div>
    );
  }
  if (!book.data) return <p className="muted center">Loading…</p>;

  const data = book.data;
  const current: Tab = tab ?? "Gradebook";

  async function exportCsv() {
    setExportError(undefined);
    try {
      const { blob, filename } = await api.courses.exportCsv(courseId);
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = filename;
      link.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      setExportError(err as Error);
    }
  }

  return (
    <div className="page">
      <div className="spread">
        <div>
          <Link href="/" className="muted">
            ← Courses
          </Link>
          <h1 style={{ marginTop: 4 }}>
            {data.course.name} <span className="muted">{data.course.term}</span>
          </h1>
        </div>
        <button type="button" onClick={exportCsv}>
          Export CSV
        </button>
      </div>
      <ErrorMessage error={exportError} />

      <div className="tabs" role="tablist">
        {TABS.map((t) => (
          <button
            key={t}
            type="button"
            role="tab"
            aria-selected={current === t}
            onClick={() => setTab(t)}
          >
            {t}
          </button>
        ))}
      </div>

      {current === "Gradebook" && (
        <GradeGrid book={data} onSaved={book.reload} onShowStats={setStatsFor} />
      )}
      {current === "Roster" && (
        <RosterPanel
          courseId={courseId}
          students={data.students.map((row) => row.student)}
          onChanged={book.reload}
        />
      )}
      {current === "Setup" && (
        <SetupPanel
          course={data.course}
          categories={data.categories}
          assignments={data.assignments}
          onChanged={book.reload}
        />
      )}
      {statsFor && <StatsPanel assignment={statsFor} version={data} onClose={closeStats} />}
    </div>
  );
}
