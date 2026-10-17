import { ApiError } from "@/lib/api";

export function ErrorMessage({ error }: { error: Error | string | null | undefined }) {
  if (!error) return null;
  const text = typeof error === "string" ? error : error.message;
  const lines = error instanceof ApiError ? error.csvErrors : [];
  return (
    <div className="error" role="alert">
      <p>{text}</p>
      {lines.length > 0 && (
        <ul>
          {lines.map((line) => (
            <li key={`${line.line}-${line.error}`}>
              Line {line.line}: {line.error}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
