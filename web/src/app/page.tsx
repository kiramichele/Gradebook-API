"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";

import { RequireAuth } from "@/components/AuthProvider";
import { ErrorMessage } from "@/components/ErrorMessage";
import { api } from "@/lib/api";
import { useAsync } from "@/lib/useAsync";

export default function HomePage() {
  return (
    <RequireAuth>
      <Courses />
    </RequireAuth>
  );
}

function Courses() {
  const courses = useAsync(() => api.courses.list(), []);
  const router = useRouter();
  const [name, setName] = useState("");
  const [term, setTerm] = useState("");
  const [error, setError] = useState<Error>();

  async function create(event: FormEvent) {
    event.preventDefault();
    try {
      const course = await api.courses.create({ name, term });
      router.push(`/courses/${course.id}`);
    } catch (err) {
      setError(err as Error);
    }
  }

  return (
    <div className="page">
      <h1>Your courses</h1>
      <ErrorMessage error={courses.error} />
      {courses.data?.length === 0 && <p className="muted">No courses yet. Create your first one below.</p>}
      <ul className="course-list">
        {courses.data?.map((course) => (
          <li key={course.id}>
            <Link href={`/courses/${course.id}`} className="card course-card">
              <strong>{course.name}</strong>
              {course.term && <span className="muted">{course.term}</span>}
            </Link>
          </li>
        ))}
      </ul>

      <form onSubmit={create} className="card inline-form" aria-label="New course">
        <h2>New course</h2>
        <label>
          Name
          <input required value={name} onChange={(e) => setName(e.target.value)} placeholder="Algebra II" />
        </label>
        <label>
          Term
          <input value={term} onChange={(e) => setTerm(e.target.value)} placeholder="Fall 2026" />
        </label>
        <button type="submit" className="primary">
          Create course
        </button>
        <ErrorMessage error={error} />
      </form>
    </div>
  );
}
