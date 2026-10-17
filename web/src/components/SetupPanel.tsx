"use client";

import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";

import { api } from "@/lib/api";
import type { Assignment, Category, Course } from "@/lib/types";

import { ErrorMessage } from "./ErrorMessage";

type Props = {
  course: Course;
  categories: Category[];
  assignments: Assignment[];
  onChanged: () => Promise<void>;
};

/** Run a mutation, then refresh; surface failures instead of throwing. */
function useMutation(onChanged: () => Promise<void>) {
  const [error, setError] = useState<Error>();
  async function run(fn: () => Promise<unknown>): Promise<boolean> {
    setError(undefined);
    try {
      await fn();
      await onChanged();
      return true;
    } catch (err) {
      setError(err as Error);
      await onChanged().catch(() => undefined);
      return false;
    }
  }
  return { error, run };
}

export function SetupPanel({ course, categories, assignments, onChanged }: Props) {
  return (
    <div className="stack">
      <div className="columns">
        <Categories course={course} categories={categories} onChanged={onChanged} />
        <CourseDetails course={course} onChanged={onChanged} />
      </div>
      <Assignments
        course={course}
        categories={categories}
        assignments={assignments}
        onChanged={onChanged}
      />
    </div>
  );
}

function Categories({ course, categories, onChanged }: Omit<Props, "assignments">) {
  const { error, run } = useMutation(onChanged);
  const [name, setName] = useState("");
  const [weight, setWeight] = useState("");
  const [drop, setDrop] = useState("0");
  const total = categories.reduce((sum, c) => sum + c.weight, 0);

  async function add(event: FormEvent) {
    event.preventDefault();
    const ok = await run(() =>
      api.categories.create(course.id, { name, weight, drop_lowest: Number(drop) }),
    );
    if (ok) {
      setName("");
      setWeight("");
      setDrop("0");
    }
  }

  return (
    <section className="card" aria-label="Categories">
      <h2>Grading categories</h2>
      <p className="muted" style={{ marginTop: 0 }}>
        Weights are relative{total ? ` (these add up to ${Math.round(total * 1000) / 1000})` : ""}.
        A category with nothing graded yet doesn&apos;t count, and its weight is shared out.
      </p>
      <ErrorMessage error={error} />
      <table className="plain">
        <thead>
          <tr>
            <th>Name</th>
            <th className="num">Weight</th>
            <th className="num">Drop lowest</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {categories.map((c) => (
            <tr key={c.id}>
              <td>
                <SavingInput
                  label={`${c.name} name`}
                  value={c.name}
                  onSave={(v) => run(() => api.categories.update(c.id, { name: v }))}
                />
              </td>
              <td className="num" style={{ width: 90 }}>
                <SavingInput
                  label={`${c.name} weight`}
                  value={String(c.weight)}
                  inputMode="decimal"
                  onSave={(v) => run(() => api.categories.update(c.id, { weight: v }))}
                />
              </td>
              <td className="num" style={{ width: 110 }}>
                <SavingInput
                  label={`${c.name} drop lowest`}
                  value={String(c.drop_lowest)}
                  inputMode="numeric"
                  onSave={(v) => run(() => api.categories.update(c.id, { drop_lowest: Number(v) }))}
                />
              </td>
              <td className="num">
                <button
                  type="button"
                  className="link danger"
                  onClick={() => run(() => api.categories.remove(c.id))}
                >
                  Delete
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <form className="row" style={{ marginTop: 12, alignItems: "flex-end" }} onSubmit={add}>
        <label style={{ flex: 2 }}>
          New category
          <input required value={name} onChange={(e) => setName(e.target.value)} placeholder="Tests" />
        </label>
        <label style={{ flex: 1 }}>
          Weight
          <input
            required
            inputMode="decimal"
            value={weight}
            onChange={(e) => setWeight(e.target.value)}
            placeholder="40"
          />
        </label>
        <label style={{ flex: 1 }}>
          Drop lowest
          <input inputMode="numeric" value={drop} onChange={(e) => setDrop(e.target.value)} />
        </label>
        <button type="submit" className="primary">
          Add
        </button>
      </form>
    </section>
  );
}

function Assignments({ course, categories, assignments, onChanged }: Props) {
  const { error, run } = useMutation(onChanged);
  const [title, setTitle] = useState("");
  const [categoryId, setCategoryId] = useState("");
  const [points, setPoints] = useState("");
  const [due, setDue] = useState("");
  const selectedCategory = categoryId || categories[0]?.id || "";

  async function add(event: FormEvent) {
    event.preventDefault();
    const ok = await run(() =>
      api.assignments.create(course.id, {
        title,
        category_id: selectedCategory,
        points_possible: points,
        due_date: due || null,
      }),
    );
    if (ok) {
      setTitle("");
      setPoints("");
      setDue("");
    }
  }

  return (
    <section className="card" aria-label="Assignments">
      <h2>Assignments</h2>
      <ErrorMessage error={error} />
      {assignments.length > 0 && (
        <table className="plain">
          <thead>
            <tr>
              <th>Title</th>
              <th>Category</th>
              <th className="num">Points</th>
              <th>Due</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {assignments.map((a) => (
              <tr key={a.id}>
                <td>
                  <SavingInput
                    label={`${a.title} title`}
                    value={a.title}
                    onSave={(v) => run(() => api.assignments.update(a.id, { title: v }))}
                  />
                </td>
                <td>
                  <select
                    aria-label={`${a.title} category`}
                    value={a.category_id}
                    onChange={(e) =>
                      run(() => api.assignments.update(a.id, { category_id: e.target.value }))
                    }
                  >
                    {categories.map((c) => (
                      <option key={c.id} value={c.id}>
                        {c.name}
                      </option>
                    ))}
                  </select>
                </td>
                <td className="num" style={{ width: 100 }}>
                  <SavingInput
                    label={`${a.title} points`}
                    value={String(a.points_possible)}
                    inputMode="decimal"
                    onSave={(v) => run(() => api.assignments.update(a.id, { points_possible: v }))}
                  />
                </td>
                <td style={{ width: 160 }}>
                  <input
                    type="date"
                    aria-label={`${a.title} due date`}
                    value={a.due_date ?? ""}
                    onChange={(e) =>
                      run(() => api.assignments.update(a.id, { due_date: e.target.value || null }))
                    }
                  />
                </td>
                <td className="num">
                  <button
                    type="button"
                    className="link danger"
                    onClick={() => {
                      if (confirm(`Delete ${a.title} and all of its grades?`)) {
                        void run(() => api.assignments.remove(a.id));
                      }
                    }}
                  >
                    Delete
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {categories.length === 0 ? (
        <p className="muted">Add a grading category first.</p>
      ) : (
        <form className="row" style={{ marginTop: 12, alignItems: "flex-end" }} onSubmit={add}>
          <label style={{ flex: 3 }}>
            New assignment
            <input required value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Quiz 1" />
          </label>
          <label style={{ flex: 2 }}>
            Category
            <select value={selectedCategory} onChange={(e) => setCategoryId(e.target.value)}>
              {categories.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </select>
          </label>
          <label style={{ flex: 1 }}>
            Points
            <input
              required
              inputMode="decimal"
              value={points}
              onChange={(e) => setPoints(e.target.value)}
              placeholder="20"
            />
          </label>
          <label style={{ flex: 2 }}>
            Due
            <input type="date" value={due} onChange={(e) => setDue(e.target.value)} />
          </label>
          <button type="submit" className="primary">
            Add
          </button>
        </form>
      )}
    </section>
  );
}

function CourseDetails({ course, onChanged }: { course: Course; onChanged: () => Promise<void> }) {
  const { error, run } = useMutation(onChanged);
  const router = useRouter();

  async function remove() {
    if (!confirm(`Delete ${course.name}? This removes its categories, assignments and grades.`)) {
      return;
    }
    try {
      await api.courses.remove(course.id);
      router.push("/");
    } catch (err) {
      alert((err as Error).message);
    }
  }

  return (
    <section className="card stack" aria-label="Course details">
      <h2>Course</h2>
      <ErrorMessage error={error} />
      <label>
        Name
        <SavingInput
          label="Course name"
          value={course.name}
          onSave={(v) => run(() => api.courses.update(course.id, { name: v }))}
        />
      </label>
      <label>
        Term
        <SavingInput
          label="Course term"
          value={course.term}
          onSave={(v) => run(() => api.courses.update(course.id, { term: v }))}
        />
      </label>
      <div>
        <button type="button" className="danger" onClick={remove}>
          Delete course
        </button>
      </div>
    </section>
  );
}

/** A text input that saves on blur or Enter when its value changed, and reverts on failure. */
function SavingInput({
  label,
  value,
  onSave,
  inputMode,
}: {
  label: string;
  value: string;
  onSave: (value: string) => Promise<boolean>;
  inputMode?: "decimal" | "numeric";
}) {
  const [draft, setDraft] = useState(value);
  const [synced, setSynced] = useState(value);
  if (value !== synced) {
    // The server value changed (e.g. after a refresh): show it.
    setSynced(value);
    setDraft(value);
  }

  async function save() {
    const next = draft.trim();
    if (next === value) return;
    if (!(await onSave(next))) setDraft(value);
  }

  return (
    <input
      aria-label={label}
      value={draft}
      inputMode={inputMode}
      onChange={(e) => setDraft(e.target.value)}
      onBlur={save}
      onKeyDown={(e) => {
        if (e.key === "Enter") (e.target as HTMLInputElement).blur();
        if (e.key === "Escape") setDraft(value);
      }}
    />
  );
}
