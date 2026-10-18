// Typed client for the Gradebook API. Every request carries the signed-in
// teacher's Supabase access token; the API and Postgres RLS do the rest.
import { supabase } from "./supabase";
import type {
  Assignment,
  AssignmentCreate,
  AssignmentStats,
  AssignmentUpdate,
  Category,
  CategoryCreate,
  CategoryUpdate,
  Course,
  CourseCreate,
  CourseUpdate,
  EnrollResult,
  Grade,
  GradeInput,
  Gradebook,
  RosterImportResult,
  Student,
  StudentCreate,
  StudentReport,
  Teacher,
} from "./types";

// Tolerate the ways this gets mis-set in a hosting dashboard: blank, quoted,
// padded, or a bare domain like "my-api.up.railway.app" with no scheme.
function apiBaseUrl(raw: string | undefined): string {
  let value = (raw ?? "").trim().replace(/^["']|["']$/g, "").trim();
  if (!value) value = "http://localhost:8000";
  if (!/^https?:\/\//i.test(value)) value = `https://${value}`;
  return value.replace(/\/+$/, "");
}

const API_URL = apiBaseUrl(process.env.NEXT_PUBLIC_API_URL);

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly detail: unknown,
  ) {
    super(describe(status, detail));
    this.name = "ApiError";
  }

  /** Line-numbered problems from a rejected CSV import, if that's what this is. */
  get csvErrors(): { line: number; error: string }[] {
    const detail = this.detail as { errors?: { line: number; error: string }[] } | undefined;
    return Array.isArray(detail?.errors) ? detail.errors : [];
  }
}

function describe(status: number, detail: unknown): string {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    // FastAPI validation errors: [{loc: [...], msg: "..."}]
    return detail
      .map((d: { loc?: unknown[]; msg?: string }) => {
        const field = d.loc?.filter((part) => part !== "body").join(".");
        return field ? `${field}: ${d.msg}` : d.msg;
      })
      .join("; ");
  }
  if (detail && typeof detail === "object" && "message" in detail) {
    return String((detail as { message: unknown }).message);
  }
  return `Request failed (${status})`;
}

type Query = Record<string, string | number | boolean | null | undefined>;

async function request(
  method: string,
  path: string,
  options: { json?: unknown; form?: FormData; query?: Query } = {},
): Promise<Response> {
  const { data } = await supabase().auth.getSession();
  const token = data.session?.access_token;
  if (!token) throw new ApiError(401, "You're signed out. Sign in again.");

  let url: URL;
  try {
    url = new URL(API_URL + path);
  } catch {
    throw new ApiError(0, `NEXT_PUBLIC_API_URL isn't a valid URL ("${API_URL}"). Fix it and redeploy.`);
  }
  for (const [key, value] of Object.entries(options.query ?? {})) {
    if (value != null) url.searchParams.set(key, String(value));
  }
  const headers: Record<string, string> = { Authorization: `Bearer ${token}` };
  let body: BodyInit | undefined;
  if (options.json !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(options.json);
  } else if (options.form) {
    body = options.form;
  }

  let response: Response;
  try {
    response = await fetch(url, { method, headers, body });
  } catch {
    throw new ApiError(0, `Can't reach the API at ${API_URL}. Is it running?`);
  }
  if (!response.ok) {
    let detail: unknown = response.statusText;
    try {
      detail = (await response.json()).detail;
    } catch {
      // Not JSON; keep the status text.
    }
    throw new ApiError(response.status, detail);
  }
  return response;
}

async function json<T>(method: string, path: string, options?: Parameters<typeof request>[2]) {
  return (await (await request(method, path, options)).json()) as T;
}

async function none(method: string, path: string) {
  await request(method, path);
}

export const api = {
  me: () => json<Teacher>("GET", "/me"),

  courses: {
    list: () => json<Course[]>("GET", "/courses"),
    get: (id: string) => json<Course>("GET", `/courses/${id}`),
    create: (body: CourseCreate) => json<Course>("POST", "/courses", { json: body }),
    update: (id: string, body: CourseUpdate) => json<Course>("PATCH", `/courses/${id}`, { json: body }),
    remove: (id: string) => none("DELETE", `/courses/${id}`),
    roster: (id: string) => json<Student[]>("GET", `/courses/${id}/students`),
    enroll: (id: string, studentIds: string[]) =>
      json<EnrollResult>("POST", `/courses/${id}/enroll`, { json: { student_ids: studentIds } }),
    unenroll: (id: string, studentId: string) =>
      none("DELETE", `/courses/${id}/students/${studentId}`),
    gradebook: (id: string) => json<Gradebook>("GET", `/courses/${id}/gradebook`),
    async exportCsv(id: string): Promise<{ blob: Blob; filename: string }> {
      const response = await request("GET", `/courses/${id}/gradebook/export`);
      const disposition = response.headers.get("Content-Disposition") ?? "";
      const filename = /filename="([^"]+)"/.exec(disposition)?.[1] ?? "gradebook.csv";
      return { blob: await response.blob(), filename };
    },
  },

  students: {
    list: () => json<Student[]>("GET", "/students"),
    create: (body: StudentCreate) => json<Student>("POST", "/students", { json: body }),
    remove: (id: string) => none("DELETE", `/students/${id}`),
    report: (id: string) => json<StudentReport>("GET", `/students/${id}/report`),
    importCsv(file: File, options: { courseId?: string; dryRun?: boolean } = {}) {
      const form = new FormData();
      form.append("file", file);
      return json<RosterImportResult>("POST", "/students/import", {
        form,
        query: { course_id: options.courseId, dry_run: options.dryRun },
      });
    },
  },

  categories: {
    create: (courseId: string, body: CategoryCreate) =>
      json<Category>("POST", `/courses/${courseId}/categories`, { json: body }),
    update: (id: string, body: CategoryUpdate) =>
      json<Category>("PATCH", `/categories/${id}`, { json: body }),
    remove: (id: string) => none("DELETE", `/categories/${id}`),
  },

  assignments: {
    create: (courseId: string, body: AssignmentCreate) =>
      json<Assignment>("POST", `/courses/${courseId}/assignments`, { json: body }),
    update: (id: string, body: AssignmentUpdate) =>
      json<Assignment>("PATCH", `/assignments/${id}`, { json: body }),
    remove: (id: string) => none("DELETE", `/assignments/${id}`),
    stats: (id: string, includeMissing = false) =>
      json<AssignmentStats>("GET", `/assignments/${id}/stats`, {
        query: { include_missing: includeMissing },
      }),
  },

  grades: {
    put: (assignmentId: string, grades: GradeInput[]) =>
      json<Grade[]>("PUT", "/grades", { json: { assignment_id: assignmentId, grades } }),
    clear: (assignmentId: string, studentId: string) =>
      none("DELETE", `/assignments/${assignmentId}/grades/${studentId}`),
  },
};
