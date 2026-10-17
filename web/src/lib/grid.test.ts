import { describe, expect, it } from "vitest";

import { move, parseClipboard, planPaste } from "./grid";

describe("move", () => {
  const at = (row: number, col: number) => ({ row, col });

  it("moves with arrows and stops at the edges", () => {
    expect(move(at(1, 1), "ArrowUp", false, 3, 3)).toEqual(at(0, 1));
    expect(move(at(0, 1), "ArrowUp", false, 3, 3)).toEqual(at(0, 1));
    expect(move(at(2, 2), "ArrowRight", false, 3, 3)).toEqual(at(2, 2));
    expect(move(at(2, 2), "ArrowDown", false, 3, 3)).toEqual(at(2, 2));
    expect(move(at(0, 0), "ArrowLeft", false, 3, 3)).toEqual(at(0, 0));
  });

  it("Enter moves down a column, Shift+Enter up", () => {
    expect(move(at(0, 2), "Enter", false, 3, 3)).toEqual(at(1, 2));
    expect(move(at(1, 2), "Enter", true, 3, 3)).toEqual(at(0, 2));
  });

  it("Tab wraps across rows", () => {
    expect(move(at(0, 2), "Tab", false, 3, 3)).toEqual(at(1, 0));
    expect(move(at(1, 0), "Tab", true, 3, 3)).toEqual(at(0, 2));
    expect(move(at(2, 2), "Tab", false, 3, 3)).toEqual(at(2, 2));
    expect(move(at(0, 0), "Tab", true, 3, 3)).toEqual(at(0, 0));
  });

  it("Home and End jump within the row", () => {
    expect(move(at(1, 1), "Home", false, 3, 4)).toEqual(at(1, 0));
    expect(move(at(1, 1), "End", false, 3, 4)).toEqual(at(1, 3));
  });

  it("ignores other keys and empty grids", () => {
    expect(move(at(0, 0), "a", false, 3, 3)).toBeNull();
    expect(move(at(0, 0), "ArrowDown", false, 0, 3)).toBeNull();
  });
});

describe("parseClipboard", () => {
  it("splits rows and tabs, ignoring the trailing newline spreadsheets add", () => {
    expect(parseClipboard("1\t2\r\n3\t4\r\n")).toEqual([
      ["1", "2"],
      ["3", "4"],
    ]);
  });

  it("handles a single value and a single column", () => {
    expect(parseClipboard("9")).toEqual([["9"]]);
    expect(parseClipboard("9\n8\nM\n")).toEqual([["9"], ["8"], ["M"]]);
  });

  it("keeps blank cells, which clear grades", () => {
    expect(parseClipboard("\t5\n")).toEqual([["", "5"]]);
  });
});

describe("planPaste", () => {
  const students = ["s0", "s1", "s2"];
  const assignments = ["a0", "a1"];

  it("groups upserts by assignment", () => {
    const plan = planPaste([["9", "8L"], ["M", "EX"]], { row: 0, col: 0 }, students, assignments);
    expect(plan.errors).toEqual([]);
    expect(plan.cells).toBe(4);
    expect(plan.upserts.get("a0")).toEqual([
      { student_id: "s0", status: "graded", score: "9" },
      { student_id: "s1", status: "missing", score: null },
    ]);
    expect(plan.upserts.get("a1")).toEqual([
      { student_id: "s0", status: "late", score: "8" },
      { student_id: "s1", status: "excused", score: null },
    ]);
  });

  it("anchors at the active cell and clips at the grid's edge", () => {
    const plan = planPaste([["1", "2"], ["3", "4"], ["5", "6"]], { row: 1, col: 1 }, students, assignments);
    expect(plan.cells).toBe(2);
    expect([...plan.upserts.keys()]).toEqual(["a1"]);
    expect(plan.upserts.get("a1")!.map((g) => g.student_id)).toEqual(["s1", "s2"]);
  });

  it("turns blanks into clears", () => {
    const plan = planPaste([[""], ["7"]], { row: 0, col: 0 }, students, assignments);
    expect(plan.clears).toEqual([{ assignmentId: "a0", studentId: "s0" }]);
    expect(plan.upserts.get("a0")).toHaveLength(1);
  });

  it("reports every invalid cell with its position", () => {
    const plan = planPaste([["9", "oops"], ["-1", "8"]], { row: 0, col: 0 }, students, assignments);
    expect(plan.errors.map((e) => e.pos)).toEqual([
      { row: 0, col: 1 },
      { row: 1, col: 0 },
    ]);
  });
});
