"use client";

import Link from "next/link";
import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ClipboardEvent,
  type KeyboardEvent,
} from "react";

import { api, ApiError } from "@/lib/api";
import { CELL_HELP, cellInput, cellText, isChange, parseCell, type ParsedCell } from "@/lib/cells";
import { percent, shortDate } from "@/lib/format";
import { move, parseClipboard, planPaste, type Pos } from "@/lib/grid";
import type { Assignment, Cell, Gradebook } from "@/lib/types";

type Props = {
  book: Gradebook;
  /** Refetch the gradebook so computed percents reflect saved grades. */
  onSaved: () => Promise<void>;
  onShowStats: (assignment: Assignment) => void;
};

type Status = { kind: "idle" | "saving" | "saved" | "error"; text?: string };

const key = (studentId: string, assignmentId: string) => `${studentId}:${assignmentId}`;

function optimistic(parsed: Exclude<ParsedCell, { kind: "invalid" }>): Cell | null {
  if (parsed.kind === "clear") return null;
  return { status: parsed.status, score: parsed.score === null ? null : Number(parsed.score) };
}

export function GradeGrid({ book, onSaved, onShowStats }: Props) {
  const students = book.students;
  const assignments = book.assignments;
  const rows = students.length;
  const cols = assignments.length;

  const [active, setActive] = useState<Pos | null>(null);
  const [editing, setEditing] = useState<{ pos: Pos; value: string } | null>(null);
  const [invalid, setInvalid] = useState<Pos | null>(null);
  const [status, setStatus] = useState<Status>({ kind: "idle" });
  // Edits shown before the server confirms them. null means "cleared".
  const [pending, setPending] = useState<Map<string, Cell | null>>(new Map());

  const wrapRef = useRef<HTMLDivElement>(null);
  const cellRefs = useRef(new Map<string, HTMLTableCellElement>());
  const editingRef = useRef(editing);
  editingRef.current = editing;
  // Writes run one at a time, in the order the teacher made them.
  const queue = useRef<Promise<void>>(Promise.resolve());
  const inFlight = useRef(0);

  const categoryName = useMemo(
    () => new Map(book.categories.map((c) => [c.id, c.name])),
    [book.categories],
  );
  const dropped = useMemo(() => {
    const set = new Set<string>();
    for (const row of students) {
      for (const category of row.categories) {
        for (const assignmentId of category.dropped) set.add(key(row.student.id, assignmentId));
      }
    }
    return set;
  }, [students]);

  const cellAt = useCallback(
    (pos: Pos): Cell | null | undefined => {
      const row = students[pos.row];
      const assignment = assignments[pos.col];
      if (!row || !assignment) return undefined;
      const k = key(row.student.id, assignment.id);
      return pending.has(k) ? pending.get(k) : row.grades[assignment.id];
    },
    [students, assignments, pending],
  );

  // Keep the active cell in bounds when students or assignments change.
  useEffect(() => {
    if (active && (active.row >= rows || active.col >= cols)) setActive(null);
  }, [active, rows, cols]);

  useEffect(() => {
    if (!active) return;
    cellRefs.current
      .get(`${active.row}:${active.col}`)
      ?.scrollIntoView({ block: "nearest", inline: "nearest" });
  }, [active]);

  const focusGrid = () => wrapRef.current?.focus({ preventScroll: true });

  /** Queue API writes, show them optimistically, then refetch computed grades. */
  function save(changes: Map<string, Cell | null>, write: () => Promise<void>) {
    setPending((prev) => new Map([...prev, ...changes]));
    setStatus({ kind: "saving", text: "Saving…" });
    inFlight.current += 1;
    queue.current = queue.current.then(async () => {
      try {
        await write();
        await onSaved();
        if (inFlight.current === 1) setStatus({ kind: "saved", text: "All changes saved" });
      } catch (err) {
        setStatus({ kind: "error", text: (err as Error).message });
        await onSaved().catch(() => undefined);
      } finally {
        inFlight.current -= 1;
        setPending((prev) => {
          const next = new Map(prev);
          for (const [k, value] of changes) if (next.get(k) === value) next.delete(k);
          return next;
        });
      }
    });
  }

  /** Save one cell's text. Returns false (and keeps editing) if it doesn't parse. */
  function commit(pos: Pos, text: string): boolean {
    const parsed = parseCell(text);
    if (parsed.kind === "invalid") {
      setInvalid(pos);
      setStatus({ kind: "error", text: parsed.message });
      return false;
    }
    setInvalid(null);
    const current = cellAt(pos);
    if (!isChange(parsed, current)) return true;

    const studentId = students[pos.row]!.student.id;
    const assignmentId = assignments[pos.col]!.id;
    save(new Map([[key(studentId, assignmentId), optimistic(parsed)]]), async () => {
      if (parsed.kind === "clear") {
        await api.grades.clear(assignmentId, studentId).catch((err) => {
          // Already cleared elsewhere; nothing to do.
          if (!(err instanceof ApiError && err.status === 404)) throw err;
        });
      } else {
        await api.grades.put(assignmentId, [
          { student_id: studentId, status: parsed.status, score: parsed.score },
        ]);
      }
    });
    return true;
  }

  function finishEditing(next: Pos | null) {
    const current = editingRef.current;
    if (!current) return;
    if (!commit(current.pos, current.value)) return;
    // Moving focus back to the grid blurs the input, which calls this again
    // before React re-renders; clearing the ref now makes that a no-op.
    editingRef.current = null;
    setEditing(null);
    if (next) setActive(next);
    focusGrid();
  }

  function startEditing(pos: Pos, value?: string) {
    setActive(pos);
    setInvalid(null);
    setEditing({ pos, value: value ?? cellInput(cellAt(pos)) });
  }

  function onGridKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    if (editing || !active) {
      if (!active && rows && cols && event.key.startsWith("Arrow")) {
        event.preventDefault();
        setActive({ row: 0, col: 0 });
      }
      return;
    }
    if (event.metaKey || event.ctrlKey || event.altKey) return;

    const next = event.key === "Enter" ? null : move(active, event.key, event.shiftKey, rows, cols);
    if (next) {
      event.preventDefault();
      setActive(next);
      setInvalid(null);
    } else if (event.key === "Enter" || event.key === "F2") {
      event.preventDefault();
      startEditing(active);
    } else if (event.key === "Delete" || event.key === "Backspace") {
      event.preventDefault();
      commit(active, "");
    } else if (event.key === "Escape") {
      setActive(null);
    } else if (event.key.length === 1) {
      // Typing replaces the cell, like a spreadsheet.
      event.preventDefault();
      startEditing(active, event.key);
    }
  }

  function onEditorKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (!editing) return;
    event.stopPropagation();
    if (event.key === "Enter" || event.key === "Tab") {
      event.preventDefault();
      finishEditing(move(editing.pos, event.key, event.shiftKey, rows, cols));
    } else if (event.key === "Escape") {
      event.preventDefault();
      setEditing(null);
      setInvalid(null);
      setStatus({ kind: "idle" });
      focusGrid();
    }
  }

  function onPaste(event: ClipboardEvent<HTMLDivElement>) {
    if (editing || !active) return;
    event.preventDefault();
    const plan = planPaste(
      parseClipboard(event.clipboardData.getData("text/plain")),
      active,
      students.map((s) => s.student.id),
      assignments.map((a) => a.id),
    );
    if (plan.errors.length) {
      const first = plan.errors[0]!;
      setInvalid(first.pos);
      setStatus({
        kind: "error",
        text: `Nothing pasted: ${plan.errors.length} cell(s) aren't grades. ${first.message}`,
      });
      return;
    }
    if (!plan.cells) return;

    const changes = new Map<string, Cell | null>();
    for (const [assignmentId, grades] of plan.upserts) {
      for (const g of grades) {
        changes.set(key(g.student_id, assignmentId), {
          status: g.status ?? "graded",
          score: g.score == null ? null : Number(g.score),
        });
      }
    }
    for (const c of plan.clears) changes.set(key(c.studentId, c.assignmentId), null);

    save(changes, async () => {
      // One request per assignment; each is all-or-nothing on the server.
      for (const [assignmentId, grades] of plan.upserts) await api.grades.put(assignmentId, grades);
      for (const c of plan.clears) {
        await api.grades.clear(c.assignmentId, c.studentId).catch((err) => {
          if (!(err instanceof ApiError && err.status === 404)) throw err;
        });
      }
    });
  }

  function onCopy(event: ClipboardEvent<HTMLDivElement>) {
    if (editing || !active) return;
    event.preventDefault();
    event.clipboardData.setData("text/plain", cellInput(cellAt(active)));
  }

  if (!cols || !rows) {
    return (
      <div className="card muted">
        {!book.categories.length
          ? "Start in Setup: add grading categories (like Tests 40%), then assignments."
          : !cols
            ? "No assignments yet. Add some in Setup."
            : "No students yet. Add or import them in Roster."}
      </div>
    );
  }

  return (
    <div>
      <div
        ref={wrapRef}
        className="grid-wrap"
        tabIndex={0}
        role="application"
        aria-label="Grade grid. Arrow keys move, type to enter a grade, Enter to edit, paste from a spreadsheet."
        onKeyDown={onGridKeyDown}
        onPaste={onPaste}
        onCopy={onCopy}
      >
        <table className="grid" role="grid" aria-rowcount={rows + 1}>
          <thead>
            <tr>
              <th className="sticky-col" scope="col">
                Student
              </th>
              {assignments.map((a) => (
                <th key={a.id} scope="col">
                  <button
                    type="button"
                    className="col-head"
                    onClick={() => onShowStats(a)}
                    title={`${a.title}: show stats`}
                  >
                    <span className="title">{a.title}</span>
                    <span className="meta">
                      {categoryName.get(a.category_id)} · {a.points_possible} pts
                      {a.due_date ? ` · ${shortDate(a.due_date)}` : ""}
                    </span>
                  </button>
                </th>
              ))}
              {book.categories.map((c) => (
                <th key={c.id} scope="col" className="summary-head" title={`${c.name} average`}>
                  {c.name}
                  <span className="muted"> {c.weight}%</span>
                </th>
              ))}
              <th scope="col" className="summary-head">
                Course
              </th>
            </tr>
          </thead>
          <tbody>
            {students.map((row, r) => {
              const results = new Map(row.categories.map((c) => [c.category_id, c]));
              return (
                <tr key={row.student.id}>
                  <th scope="row" className="sticky-col">
                    <Link href={`/students/${row.student.id}`}>{row.student.name}</Link>
                  </th>
                  {assignments.map((a, c) => {
                    const pos = { row: r, col: c };
                    const k = key(row.student.id, a.id);
                    const cell = cellAt(pos);
                    const isActive = active?.row === r && active.col === c;
                    const isEditing = editing?.pos.row === r && editing.pos.col === c;
                    const classes = [
                      "cell",
                      cell?.status,
                      dropped.has(k) && !pending.has(k) ? "dropped" : "",
                      pending.has(k) ? "pending" : "",
                      isActive ? "active" : "",
                      invalid?.row === r && invalid.col === c ? "invalid" : "",
                    ];
                    return (
                      <td
                        key={a.id}
                        ref={(el) => {
                          if (el) cellRefs.current.set(`${r}:${c}`, el);
                          else cellRefs.current.delete(`${r}:${c}`);
                        }}
                        role="gridcell"
                        aria-selected={isActive}
                        aria-label={`${row.student.name}, ${a.title}`}
                        data-row={r}
                        data-col={c}
                        className={classes.filter(Boolean).join(" ")}
                        title={
                          dropped.has(k)
                            ? "Dropped: lowest in its category"
                            : cell?.status === "late"
                              ? "Late"
                              : undefined
                        }
                        onMouseDown={(event) => {
                          if (isEditing) return;
                          event.preventDefault();
                          if (editing) finishEditing(null);
                          setActive(pos);
                          setInvalid(null);
                          focusGrid();
                        }}
                        onDoubleClick={() => startEditing(pos)}
                      >
                        {isEditing ? (
                          <input
                            autoFocus
                            aria-label={`Grade for ${row.student.name}, ${a.title}`}
                            value={editing.value}
                            onChange={(e) => setEditing({ pos, value: e.target.value })}
                            onKeyDown={onEditorKeyDown}
                            onBlur={() => finishEditing(null)}
                          />
                        ) : (
                          cellText(cell)
                        )}
                      </td>
                    );
                  })}
                  {book.categories.map((c) => (
                    <td key={c.id} className="summary">
                      {percent(results.get(c.id)?.percent)}
                    </td>
                  ))}
                  <td className="summary course" data-testid="course-grade">
                    {percent(row.percent)} {row.letter ?? ""}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <div className="grid-status" aria-live="polite">
        <span className="muted">{CELL_HELP} Paste a block from a spreadsheet to fill many at once.</span>
        {status.kind === "error" ? (
          <span className="error" role="alert">
            {status.text}
          </span>
        ) : (
          <span className="muted" data-testid="save-status">
            {status.text}
          </span>
        )}
      </div>
    </div>
  );
}
