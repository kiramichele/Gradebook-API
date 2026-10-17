"use client";

import Link from "next/link";
import { useRef, useState, type FormEvent } from "react";

import { api } from "@/lib/api";
import type { RosterImportResult, Student } from "@/lib/types";

import { ErrorMessage } from "./ErrorMessage";

type Props = {
  courseId: string;
  students: Student[];
  onChanged: () => Promise<void>;
};

export function RosterPanel({ courseId, students, onChanged }: Props) {
  return (
    <div className="columns">
      <section className="card">
        <h2>Enrolled ({students.length})</h2>
        <Roster courseId={courseId} students={students} onChanged={onChanged} />
      </section>
      <div className="stack">
        <AddStudent courseId={courseId} onChanged={onChanged} />
        <ImportRoster courseId={courseId} onChanged={onChanged} />
      </div>
    </div>
  );
}

function Roster({ courseId, students, onChanged }: Props) {
  const [error, setError] = useState<Error>();

  async function unenroll(student: Student) {
    if (!confirm(`Remove ${student.name} from this course? Their grades are kept.`)) return;
    try {
      await api.courses.unenroll(courseId, student.id);
      await onChanged();
    } catch (err) {
      setError(err as Error);
    }
  }

  if (!students.length) return <p className="muted">No students yet.</p>;
  return (
    <>
      <ErrorMessage error={error} />
      <table className="plain">
        <thead>
          <tr>
            <th>Name</th>
            <th>Email</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {students.map((s) => (
            <tr key={s.id}>
              <td>
                <Link href={`/students/${s.id}`}>{s.name}</Link>
              </td>
              <td className="muted">{s.email}</td>
              <td className="num">
                <button type="button" className="link danger" onClick={() => unenroll(s)}>
                  Remove
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </>
  );
}

function AddStudent({ courseId, onChanged }: Omit<Props, "students">) {
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [error, setError] = useState<Error>();

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError(undefined);
    try {
      const student = await api.students.create({ name, email: email || null });
      await api.courses.enroll(courseId, [student.id]);
      setName("");
      setEmail("");
      await onChanged();
    } catch (err) {
      setError(err as Error);
    }
  }

  return (
    <form className="card stack" onSubmit={submit} aria-label="Add a student">
      <h2>Add a student</h2>
      <div className="row">
        <label style={{ flex: 1 }}>
          Name
          <input required value={name} onChange={(e) => setName(e.target.value)} />
        </label>
        <label style={{ flex: 1 }}>
          Email (optional)
          <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} />
        </label>
      </div>
      <div>
        <button type="submit" className="primary">
          Add and enroll
        </button>
      </div>
      <ErrorMessage error={error} />
    </form>
  );
}

function ImportRoster({ courseId, onChanged }: Omit<Props, "students">) {
  const input = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<RosterImportResult>();
  const [error, setError] = useState<Error>();
  const [done, setDone] = useState<string>();
  const [busy, setBusy] = useState(false);

  async function check(selected: File | null) {
    setFile(selected);
    setPreview(undefined);
    setError(undefined);
    setDone(undefined);
    if (!selected) return;
    setBusy(true);
    try {
      setPreview(await api.students.importCsv(selected, { courseId, dryRun: true }));
    } catch (err) {
      setError(err as Error);
    } finally {
      setBusy(false);
    }
  }

  async function confirmImport() {
    if (!file) return;
    setBusy(true);
    try {
      const result = await api.students.importCsv(file, { courseId });
      setDone(
        `Imported: ${result.created.length} new, ${result.existing.length} already on file, ` +
          `${result.enrolled.length} enrolled.`,
      );
      setPreview(undefined);
      setFile(null);
      if (input.current) input.current.value = "";
      await onChanged();
    } catch (err) {
      setError(err as Error);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="card stack" aria-label="Import a roster">
      <h2>Import a roster (CSV)</h2>
      <p className="muted" style={{ margin: 0 }}>
        Needs a <code>name</code> column (or first and last name) and optionally <code>email</code>.
        Students already on file are matched by email, so re-importing is safe.
      </p>
      <input
        ref={input}
        type="file"
        accept=".csv,text/csv"
        aria-label="Roster CSV file"
        onChange={(e) => check(e.target.files?.[0] ?? null)}
      />
      {busy && <p className="muted">Checking…</p>}
      <ErrorMessage error={error} />
      {done && <p className="notice">{done}</p>}
      {preview && (
        <div className="notice" data-testid="import-preview">
          <p style={{ margin: "0 0 6px" }}>
            Ready: <strong>{preview.created.length}</strong> new student(s),{" "}
            <strong>{preview.existing.length}</strong> already on file,{" "}
            <strong>{preview.enrolled.length}</strong> to enroll
            {preview.already_enrolled.length ? `, ${preview.already_enrolled.length} already enrolled` : ""}.
          </p>
          {preview.created.length > 0 && (
            <p className="muted" style={{ margin: "0 0 8px" }}>
              New: {preview.created.map((s) => s.name).join(", ")}
            </p>
          )}
          <button type="button" className="primary" onClick={confirmImport} disabled={busy}>
            Import
          </button>
        </div>
      )}
    </section>
  );
}
