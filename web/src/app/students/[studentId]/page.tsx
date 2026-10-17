"use client";

import Link from "next/link";
import { useParams } from "next/navigation";

import { RequireAuth } from "@/components/AuthProvider";
import { ErrorMessage } from "@/components/ErrorMessage";
import { api } from "@/lib/api";
import { formatScore } from "@/lib/cells";
import { number, percent, shortDate, weightShare } from "@/lib/format";
import type { ReportAssignment, ReportCourse } from "@/lib/types";
import { useAsync } from "@/lib/useAsync";

export default function StudentReportPage() {
  return (
    <RequireAuth>
      <Report />
    </RequireAuth>
  );
}

function Report() {
  const { studentId } = useParams<{ studentId: string }>();
  const report = useAsync(() => api.students.report(studentId), [studentId]);

  if (report.error) return <ErrorMessage error={report.error} />;
  if (!report.data) return <p className="muted center">Loading…</p>;
  const { student, courses } = report.data;

  return (
    <div className="page narrow">
      <h1 style={{ marginBottom: 0 }}>{student.name}</h1>
      {student.email && <p className="muted" style={{ marginTop: 4 }}>{student.email}</p>}
      {courses.length === 0 && <p className="muted">Not enrolled in any courses.</p>}
      <div className="stack">
        {courses.map((course) => (
          <CourseReport key={course.course.id} report={course} />
        ))}
      </div>
    </div>
  );
}

function CourseReport({ report }: { report: ReportCourse }) {
  return (
    <section className="card" aria-label={report.course.name}>
      <div className="spread">
        <h2 style={{ margin: 0 }}>
          <Link href={`/courses/${report.course.id}`}>{report.course.name}</Link>{" "}
          <span className="muted">{report.course.term}</span>
        </h2>
        <div className="grade-hero" data-testid="report-grade">
          {percent(report.percent)} {report.letter ?? ""}
        </div>
      </div>
      {report.categories.map((cat) => (
        <div key={cat.category.id}>
          <h3 className="spread">
            <span>
              {cat.category.name}{" "}
              <span className="muted" style={{ fontWeight: 400 }}>
                weight {cat.category.weight}
                {cat.effective_weight != null && cat.effective_weight !== cat.category.weight / 100
                  ? ` · counts ${weightShare(cat.effective_weight)} of the grade`
                  : ""}
                {cat.category.drop_lowest ? ` · drops lowest ${cat.category.drop_lowest}` : ""}
              </span>
            </span>
            <span>
              {percent(cat.percent)}
              <span className="muted" style={{ fontWeight: 400 }}>
                {" "}
                ({number(cat.earned)}/{number(cat.possible)})
              </span>
            </span>
          </h3>
          {cat.assignments.length === 0 ? (
            <p className="muted">No assignments.</p>
          ) : (
            <table className="plain fixed">
              <thead>
                <tr>
                  <th>Assignment</th>
                  <th className="col-due">Due</th>
                  <th className="num col-score">Score</th>
                  <th className="col-badge">
                    <span className="sr-only">Note</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {cat.assignments.map((row) => (
                  <tr key={row.assignment.id}>
                    <td>{row.assignment.title}</td>
                    <td className="muted">{shortDate(row.assignment.due_date)}</td>
                    <td className="num">
                      {row.score != null ? formatScore(row.score) : row.status === "missing" ? 0 : "—"}
                      <span className="muted"> / {formatScore(row.assignment.points_possible)}</span>
                    </td>
                    <td>
                      <OutcomeBadge row={row} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      ))}
    </section>
  );
}

function OutcomeBadge({ row }: { row: ReportAssignment }) {
  if (row.outcome === "dropped") return <span className="badge dropped">Dropped</span>;
  if (row.outcome === "excused") return <span className="badge excused">Excused</span>;
  if (row.outcome === "ungraded") return <span className="badge">Not graded</span>;
  if (row.status === "missing") return <span className="badge missing">Missing</span>;
  if (row.status === "late") return <span className="badge late">Late</span>;
  return null;
}
