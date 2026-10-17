// What a teacher types into a gradebook cell, and how a cell is shown.
//
//   9.5        graded, 9.5 points
//   8L, 8 late late, 8 points
//   M          missing (counts as 0)
//   EX         excused (left out of the grade)
//   (empty)    clear the grade
import type { Cell, GradeStatus } from "./types";

export type ParsedCell =
  | { kind: "clear" }
  | { kind: "grade"; status: GradeStatus; score: string | null }
  | { kind: "invalid"; message: string };

export const CELL_HELP = "Type a score, M for missing, EX for excused, or add L for late (8L).";

const MISSING = new Set(["m", "missing"]);
const EXCUSED = new Set(["ex", "exc", "excused"]);
const SCORE = /^(\d+(?:\.\d{1,2})?|\.\d{1,2})\s*(l|late)?$/;
const MAX_SCORE = 999999.99;

export function parseCell(input: string): ParsedCell {
  const text = input.trim().toLowerCase();
  if (text === "") return { kind: "clear" };
  if (MISSING.has(text)) return { kind: "grade", status: "missing", score: null };
  if (EXCUSED.has(text)) return { kind: "grade", status: "excused", score: null };

  const match = SCORE.exec(text);
  if (!match) {
    return { kind: "invalid", message: `"${input.trim()}" isn't a grade. ${CELL_HELP}` };
  }
  const score = normalizeNumber(match[1]!);
  if (Number(score) > MAX_SCORE) {
    return { kind: "invalid", message: `${score} is too large.` };
  }
  return { kind: "grade", status: match[2] ? "late" : "graded", score };
}

/** "09.50" -> "9.5", ".5" -> "0.5". Kept as a string so no float rounding reaches the API. */
export function normalizeNumber(value: string): string {
  let [whole = "", fraction = ""] = value.split(".");
  whole = whole.replace(/^0+(?=\d)/, "") || "0";
  fraction = fraction.replace(/0+$/, "");
  return fraction ? `${whole}.${fraction}` : whole;
}

export function formatScore(score: number): string {
  return String(Math.round(score * 100) / 100);
}

/** The text shown in a cell. */
export function cellText(cell: Cell | null | undefined): string {
  if (!cell) return "";
  if (cell.status === "missing") return "M";
  if (cell.status === "excused") return "EX";
  return cell.score === null ? "" : formatScore(cell.score);
}

/** The text a cell starts with when edited, which parses back to the same grade. */
export function cellInput(cell: Cell | null | undefined): string {
  if (cell?.status === "late" && cell.score !== null) return `${formatScore(cell.score)}L`;
  return cellText(cell);
}

/** Does saving `parsed` change `current`? Used to skip no-op saves. */
export function isChange(parsed: ParsedCell, current: Cell | null | undefined): boolean {
  if (parsed.kind === "invalid") return false;
  if (parsed.kind === "clear") return current != null;
  if (!current || current.status !== parsed.status) return true;
  if (parsed.score === null) return false;
  return current.score === null || Number(parsed.score) !== current.score;
}
