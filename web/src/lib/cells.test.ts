import { describe, expect, it } from "vitest";

import { cellInput, cellText, isChange, normalizeNumber, parseCell } from "./cells";

describe("parseCell", () => {
  it.each([
    ["9.5", "graded", "9.5"],
    ["  10 ", "graded", "10"],
    ["0", "graded", "0"],
    [".5", "graded", "0.5"],
    ["07.50", "graded", "7.5"],
    ["8L", "late", "8"],
    ["8 l", "late", "8"],
    ["8 late", "late", "8"],
    ["8.25LATE", "late", "8.25"],
  ])("%j is a %s score of %s", (input, status, score) => {
    expect(parseCell(input)).toEqual({ kind: "grade", status, score });
  });

  it.each(["m", "M", "missing", " Missing "])("%j is missing", (input) => {
    expect(parseCell(input)).toEqual({ kind: "grade", status: "missing", score: null });
  });

  it.each(["ex", "EX", "exc", "excused"])("%j is excused", (input) => {
    expect(parseCell(input)).toEqual({ kind: "grade", status: "excused", score: null });
  });

  it.each(["", "   "])("%j clears the cell", (input) => {
    expect(parseCell(input)).toEqual({ kind: "clear" });
  });

  it.each(["-1", "abc", "9.555", "1,5", "L8", "8LL", "9/10", "1e3", "x"])(
    "%j is invalid",
    (input) => {
      expect(parseCell(input).kind).toBe("invalid");
    },
  );

  it("rejects scores the database can't store", () => {
    expect(parseCell("1000000").kind).toBe("invalid");
    expect(parseCell("999999.99").kind).toBe("grade");
  });
});

describe("normalizeNumber", () => {
  it.each([
    ["10", "10"],
    ["010", "10"],
    ["0", "0"],
    ["00", "0"],
    ["9.50", "9.5"],
    ["9.00", "9"],
    [".25", "0.25"],
  ])("%s -> %s", (input, output) => {
    expect(normalizeNumber(input)).toBe(output);
  });
});

describe("cellText and cellInput", () => {
  it("shows statuses and scores", () => {
    expect(cellText(undefined)).toBe("");
    expect(cellText({ status: "graded", score: 9.5 })).toBe("9.5");
    expect(cellText({ status: "late", score: 8 })).toBe("8");
    expect(cellText({ status: "missing", score: null })).toBe("M");
    expect(cellText({ status: "excused", score: null })).toBe("EX");
  });

  it("round-trips through parseCell", () => {
    const cells = [
      { status: "graded", score: 9.5 },
      { status: "late", score: 8 },
      { status: "missing", score: null },
      { status: "excused", score: null },
    ] as const;
    for (const cell of cells) {
      const parsed = parseCell(cellInput(cell));
      expect(parsed).toMatchObject({ kind: "grade", status: cell.status });
      expect(isChange(parsed, cell)).toBe(false);
    }
  });
});

describe("isChange", () => {
  const nine = { status: "graded", score: 9 } as const;

  it("detects edits", () => {
    expect(isChange(parseCell("9"), nine)).toBe(false);
    expect(isChange(parseCell("9.0"), nine)).toBe(false);
    expect(isChange(parseCell("8"), nine)).toBe(true);
    expect(isChange(parseCell("9L"), nine)).toBe(true);
    expect(isChange(parseCell("M"), nine)).toBe(true);
  });

  it("treats clearing an empty cell as no change", () => {
    expect(isChange(parseCell(""), undefined)).toBe(false);
    expect(isChange(parseCell(""), nine)).toBe(true);
    expect(isChange(parseCell("5"), undefined)).toBe(true);
  });

  it("never saves invalid input", () => {
    expect(isChange(parseCell("nope"), nine)).toBe(false);
  });
});
