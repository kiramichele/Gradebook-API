// A teacher's first day, end to end: sign in, set up a course, build a roster
// (by hand and by CSV), enter grades by typing and by pasting from a
// spreadsheet, then read the stats, export, and open a student report.
import { readFile } from "node:fs/promises";

import { expect, test, type Locator, type Page } from "@playwright/test";

import { mockSupabaseAuth, newUser } from "./auth";

test.describe.configure({ mode: "serial" });

async function signIn(page: Page, name = "Ms Frizzle") {
  const user = newUser(name);
  await mockSupabaseAuth(page, user);
  await page.goto("/");
  await expect(page).toHaveURL(/\/login/);
  await page.getByLabel("Email").fill(user.email);
  await page.getByLabel("Password").fill("correct horse");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("heading", { name: "Your courses" })).toBeVisible();
  return user;
}

function cell(page: Page, row: number, col: number): Locator {
  return page.locator(`td[data-row="${row}"][data-col="${col}"]`);
}

function courseGrade(page: Page, studentName: string): Locator {
  return page.getByRole("row", { name: new RegExp(studentName) }).getByTestId("course-grade");
}

async function paste(page: Page, text: string) {
  await page.locator(".grid-wrap").evaluate((el, value) => {
    const data = new DataTransfer();
    data.setData("text/plain", value);
    el.dispatchEvent(new ClipboardEvent("paste", { clipboardData: data, bubbles: true, cancelable: true }));
  }, text);
}

async function waitForSave(page: Page) {
  await expect(page.getByTestId("save-status")).toHaveText("All changes saved");
  await expect(page.locator(".cell.pending")).toHaveCount(0);
}

test("redirects to sign-in when signed out", async ({ page }) => {
  await page.goto("/courses/00000000-0000-0000-0000-000000000000");
  await expect(page).toHaveURL(/\/login\?next=%2Fcourses%2F/);
});

test("a teacher sets up a course, grades it, and reads the results", async ({ page }) => {
  await signIn(page);

  // --- create a course; a new course opens on Setup --------------------------
  await page.getByLabel("Name").fill("Biology");
  await page.getByLabel("Term").fill("Fall 2026");
  await page.getByRole("button", { name: "Create course" }).click();
  await expect(page.getByRole("heading", { name: /Biology/ })).toBeVisible();
  await expect(page.getByRole("tab", { name: "Setup" })).toHaveAttribute("aria-selected", "true");

  // --- categories and assignments --------------------------------------------
  const categories = page.getByRole("region", { name: "Categories" });
  async function addCategory(name: string, weight: string, drop = "0") {
    await categories.getByLabel("New category").fill(name);
    await categories.getByLabel("Weight", { exact: true }).fill(weight);
    await categories.getByLabel("Drop lowest", { exact: true }).fill(drop);
    await categories.getByRole("button", { name: "Add" }).click();
    await expect(categories.getByLabel(`${name} name`)).toBeVisible();
  }
  await addCategory("Tests", "60");
  await addCategory("Homework", "40", "1");

  const assignments = page.getByRole("region", { name: "Assignments" });
  async function addAssignment(title: string, category: string, points: string, due: string) {
    await assignments.getByLabel("New assignment").fill(title);
    await assignments
      .getByRole("combobox", { name: "Category", exact: true })
      .selectOption({ label: category });
    await assignments.getByLabel("Points", { exact: true }).fill(points);
    await assignments.getByLabel("Due", { exact: true }).fill(due);
    await assignments.getByRole("button", { name: "Add" }).click();
    await expect(assignments.getByLabel(`${title} title`)).toBeVisible();
  }
  await addAssignment("HW 1", "Homework", "10", "2026-09-01");
  await addAssignment("HW 2", "Homework", "10", "2026-09-08");
  await addAssignment("Test 1", "Tests", "100", "2026-09-15");

  // --- roster: one by hand, two from a CSV (previewed first) ----------------
  await page.getByRole("tab", { name: "Roster" }).click();
  const add = page.getByRole("form", { name: "Add a student" });
  await add.getByLabel("Name").fill("Ada Lovelace");
  await add.getByLabel("Email (optional)").fill("ada@example.edu");
  await add.getByRole("button", { name: "Add and enroll" }).click();
  await expect(page.getByRole("heading", { name: "Enrolled (1)" })).toBeVisible();

  await page.getByLabel("Roster CSV file").setInputFiles({
    name: "roster.csv",
    mimeType: "text/csv",
    buffer: Buffer.from("First Name,Last Name,E-mail\nGrace,Hopper,grace@example.edu\nAlan,Turing,\n"),
  });
  const preview = page.getByTestId("import-preview");
  await expect(preview).toContainText("2 new student(s)");
  await expect(page.getByRole("heading", { name: "Enrolled (1)" })).toBeVisible(); // dry run
  await preview.getByRole("button", { name: "Import" }).click();
  await expect(page.getByRole("heading", { name: "Enrolled (3)" })).toBeVisible();

  // A bad file is rejected with line numbers and imports nothing.
  await page.getByLabel("Roster CSV file").setInputFiles({
    name: "bad.csv",
    mimeType: "text/csv",
    buffer: Buffer.from("name,email\nOk,ok@example.edu\n,nobody@example.edu\n"),
  });
  await expect(page.locator(".error[role=alert]")).toContainText("Line 3: Name is required");

  // --- gradebook: rows are Ada, Alan, Grace; columns HW 1, HW 2, Test 1 ------
  await page.getByRole("tab", { name: "Gradebook" }).click();
  await expect(page.locator("tbody tr")).toHaveCount(3);

  // Type a column of HW 1 scores: Enter commits and moves down.
  await cell(page, 0, 0).click();
  await page.keyboard.type("9");
  await page.keyboard.press("Enter");
  await page.keyboard.type("6");
  await page.keyboard.press("Enter");
  await page.keyboard.type("m");
  await page.keyboard.press("Enter");
  await waitForSave(page);
  await expect(cell(page, 2, 0)).toHaveText("M");
  await expect(cell(page, 2, 0)).toHaveClass(/missing/);

  // Paste a 3x2 block from a spreadsheet into HW 2 / Test 1.
  await cell(page, 0, 1).click();
  await paste(page, "10\t88\n4\t72L\nEX\t95\n");
  await waitForSave(page);
  await expect(cell(page, 1, 2)).toHaveText("72");
  await expect(cell(page, 1, 2)).toHaveClass(/late/);
  await expect(cell(page, 2, 1)).toHaveText("EX");

  // Ada: HW drops 9/10, keeps 10/10 = 100%; Test 88. 0.6*88 + 0.4*100 = 92.8
  await expect(courseGrade(page, "Ada Lovelace")).toHaveText("92.8% A-");
  await expect(cell(page, 0, 0)).toHaveClass(/dropped/);
  // Alan: HW drops 4/10 -> 60%; Test 72 (late). 0.6*72 + 0.4*60 = 67.2
  await expect(courseGrade(page, "Alan Turing")).toHaveText("67.2% D+");
  // Grace: HW 2 excused, HW 1 missing is all that's left (never dropped) -> 0%; Test 95. = 57
  await expect(courseGrade(page, "Grace Hopper")).toHaveText("57.0% F");

  // Invalid input is refused and nothing is saved.
  await cell(page, 0, 2).click();
  await page.keyboard.type("abc");
  await page.keyboard.press("Enter");
  await expect(page.locator(".error[role=alert]")).toContainText(`"abc" isn't a grade`);
  await expect(cell(page, 0, 2)).toHaveClass(/invalid/);
  await page.keyboard.press("Escape");
  await expect(cell(page, 0, 2)).toHaveText("88");

  // Delete clears a cell; the grade is recomputed without it.
  await cell(page, 1, 2).click();
  await page.keyboard.press("Delete");
  await waitForSave(page);
  await expect(cell(page, 1, 2)).toHaveText("");
  await expect(courseGrade(page, "Alan Turing")).toHaveText("60.0% D-");

  // Arrow keys and editing an existing value.
  await page.keyboard.press("ArrowUp");
  await page.keyboard.press("Enter");
  await expect(cell(page, 0, 2).locator("input")).toHaveValue("88");
  await page.keyboard.press("Control+A");
  await page.keyboard.type("90");
  await page.keyboard.press("Tab");
  await waitForSave(page);
  await expect(courseGrade(page, "Ada Lovelace")).toHaveText("94.0% A");

  // --- assignment stats --------------------------------------------------------
  await page.getByRole("button", { name: /^HW 1/ }).click();
  const stats = page.getByRole("complementary", { name: "Stats for HW 1" });
  const tiles = stats.getByTestId("stats-tiles");
  await expect(tiles).toContainText("Mean7.5");
  await expect(tiles).toContainText("Scores2");
  await expect(stats).toContainText("3 enrolled · 2 graded · 1 missing");
  await stats.getByLabel("Count missing work as 0").check();
  await expect(tiles).toContainText("Mean5");
  await expect(stats.getByRole("listitem", { name: "90–100%: 1 student" })).toBeVisible();
  await stats.getByRole("button", { name: "Show as table" }).click();
  await expect(stats.getByRole("cell", { name: "60–70%" })).toBeVisible();
  await stats.getByRole("button", { name: "Close stats" }).click();
  await expect(stats).toHaveCount(0);

  // --- CSV export --------------------------------------------------------------
  const downloadPromise = page.waitForEvent("download");
  await page.getByRole("button", { name: "Export CSV" }).click();
  const download = await downloadPromise;
  expect(download.suggestedFilename()).toBe("biology-fall-2026.csv");
  const csv = (await readFile((await download.path())!, "utf-8")).replace(/^﻿/, "");
  const lines = csv.trim().split(/\r?\n/);
  expect(lines[0]).toBe(
    "Student,Email,HW 1 (10 pts),HW 2 (10 pts),Test 1 (100 pts),Homework %,Tests %,Course %,Letter",
  );
  expect(lines[1]).toBe("Ada Lovelace,ada@example.edu,9,10,90,100.00,90.00,94.00,A");
  expect(lines[3]).toBe("Grace Hopper,grace@example.edu,missing,excused,95,0.00,95.00,57.00,F");

  // --- student report ----------------------------------------------------------
  await page.getByRole("link", { name: "Ada Lovelace" }).click();
  await expect(page.getByRole("heading", { name: "Ada Lovelace" })).toBeVisible();
  await expect(page.getByTestId("report-grade")).toHaveText("94.0% A");
  const homework = page.getByRole("row", { name: /HW 1/ });
  await expect(homework).toContainText("Dropped");

  // --- sign out ------------------------------------------------------------------
  await page.getByRole("button", { name: "Sign out" }).click();
  await expect(page).toHaveURL(/\/login/);
});

test("another teacher sees none of it", async ({ page }) => {
  await signIn(page, "Mr Keating");
  await expect(page.getByText("No courses yet")).toBeVisible();
});
