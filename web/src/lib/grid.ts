// Spreadsheet-style keyboard movement and clipboard paste for the grade grid.
import { parseCell, type ParsedCell } from "./cells";
import type { GradeInput } from "./types";

export type Pos = { row: number; col: number };

/** Where the active cell goes after a navigation key, or null if the key isn't one. */
export function move(
  pos: Pos,
  key: string,
  shift: boolean,
  rows: number,
  cols: number,
): Pos | null {
  if (rows === 0 || cols === 0) return null;
  const clamp = (row: number, col: number): Pos => ({
    row: Math.min(Math.max(row, 0), rows - 1),
    col: Math.min(Math.max(col, 0), cols - 1),
  });
  switch (key) {
    case "ArrowUp":
      return clamp(pos.row - 1, pos.col);
    case "ArrowDown":
      return clamp(pos.row + 1, pos.col);
    case "ArrowLeft":
      return clamp(pos.row, pos.col - 1);
    case "ArrowRight":
      return clamp(pos.row, pos.col + 1);
    case "Enter":
      // Entering a column of scores, like a spreadsheet.
      return clamp(pos.row + (shift ? -1 : 1), pos.col);
    case "Tab": {
      // Wraps to the next or previous row.
      const index = pos.row * cols + pos.col + (shift ? -1 : 1);
      const last = rows * cols - 1;
      const wrapped = Math.min(Math.max(index, 0), last);
      return { row: Math.floor(wrapped / cols), col: wrapped % cols };
    }
    case "Home":
      return clamp(pos.row, 0);
    case "End":
      return clamp(pos.row, cols - 1);
    default:
      return null;
  }
}

/** Clipboard text from a spreadsheet: rows split by newlines, cells by tabs. */
export function parseClipboard(text: string): string[][] {
  const lines = text.replace(/\r\n?/g, "\n").split("\n");
  if (lines.length > 1 && lines[lines.length - 1] === "") lines.pop();
  return lines.map((line) => line.split("\t"));
}

export type PastePlan = {
  /** Grades to upsert, grouped by assignment for PUT /grades. */
  upserts: Map<string, GradeInput[]>;
  /** Cells to clear. */
  clears: { assignmentId: string; studentId: string }[];
  /** Cells that didn't parse; when non-empty, nothing should be saved. */
  errors: { pos: Pos; message: string }[];
  /** How many cells the paste covers inside the grid. */
  cells: number;
};

/**
 * Turn a block of pasted text, anchored at `start`, into API writes. Cells
 * that would fall outside the grid are ignored, like pasting near the edge of
 * a spreadsheet.
 */
export function planPaste(
  block: string[][],
  start: Pos,
  studentIds: string[],
  assignmentIds: string[],
): PastePlan {
  const plan: PastePlan = { upserts: new Map(), clears: [], errors: [], cells: 0 };
  block.forEach((values, r) => {
    const studentId = studentIds[start.row + r];
    if (studentId === undefined) return;
    values.forEach((value, c) => {
      const assignmentId = assignmentIds[start.col + c];
      if (assignmentId === undefined) return;
      plan.cells += 1;
      const parsed: ParsedCell = parseCell(value);
      if (parsed.kind === "invalid") {
        plan.errors.push({ pos: { row: start.row + r, col: start.col + c }, message: parsed.message });
      } else if (parsed.kind === "clear") {
        plan.clears.push({ assignmentId, studentId });
      } else {
        const list = plan.upserts.get(assignmentId) ?? [];
        list.push({ student_id: studentId, status: parsed.status, score: parsed.score });
        plan.upserts.set(assignmentId, list);
      }
    });
  });
  return plan;
}
