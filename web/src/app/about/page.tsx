import type { Metadata } from "next";
import Link from "next/link";

import { API_URL } from "@/lib/api";
import { demoEnabled } from "@/lib/demo";

// The public project page: no sign-in, so it can be linked from a portfolio.
// The long-form version lives in docs/case-study.md; keep the two in step.

const REPO = "https://github.com/kiramichele/Gradebook-API";

export const metadata: Metadata = {
  title: "Gradebook: case study",
  description:
    "A teacher-built gradebook: FastAPI and Postgres with Row Level Security, a spreadsheet-style " +
    "Next.js grid, and grading rules drawn from five years in the classroom.",
};

const STACK = [
  "Python",
  "FastAPI",
  "SQLAlchemy",
  "Postgres + RLS",
  "Supabase Auth",
  "Next.js",
  "TypeScript",
  "Docker",
  "Railway",
  "Vercel",
  "GitHub Actions",
];

const RULES: { title: string; body: string }[] = [
  {
    title: "An empty category doesn't count as zero.",
    body:
      "Early in a term, one unscored category can make a grade look like a disaster. I've seen " +
      "families panic over exactly that; my own parents did it. So a category with nothing " +
      "graded yet drops out, its weight is shared among the categories that have grades, and " +
      "the report shows each category's real share so the number can be explained.",
  },
  {
    title: "Missing, excused and late are three different things.",
    body:
      "I had a student who was in and out of the hospital, and a student who always did the " +
      "work but always turned it in late. A gradebook with only “score” or “zero” punishes both " +
      "for the wrong reasons. Excused work leaves both the points earned and the points " +
      "possible. Late work keeps its full score and is only flagged. Missing is the only status " +
      "that counts as zero.",
  },
  {
    title: "Late work isn't penalized, on purpose.",
    body:
      "You never know what's going on in a student's life. A late mark is a record for the " +
      "teacher to follow up on, not a deduction.",
  },
  {
    title: "Drop lowest means what the teacher means.",
    body:
      "In my class we drop the lowest coursework grade, and nobody argues about it. But “lowest” " +
      "gets ambiguous once assignments have different point values, so the engine drops " +
      "whichever assignment helps the student most. A rule meant to help a student should " +
      "never hurt them.",
  },
  {
    title: "Class averages leave out missing work.",
    body:
      "I use assignment averages to decide what to reteach. If missing work counted as zero, an " +
      "assignment a few students never turned in would look like one the whole class " +
      "struggled with, and I'd reteach the wrong things. One toggle counts it when you want to.",
  },
  {
    title: "It works like a spreadsheet, and it takes CSV.",
    body:
      "Moving grades between systems meant copying them across by hand: slow, and easy to get " +
      "wrong. The grid takes a block pasted straight from Sheets or Excel, rosters import from " +
      "another system's CSV, and a paste with any bad cell saves nothing rather than half of it.",
  },
];

const DECISIONS: { title: string; body: string }[] = [
  {
    title: "Ownership is enforced twice",
    body:
      "Every query filters by the signed-in teacher, and Postgres Row Level Security checks it " +
      "again: each transaction runs as that teacher, so the policies apply to the API's own " +
      "queries. Another teacher's ids return 404, never 403, so ids don't leak.",
  },
  {
    title: "Misconfigurations can't ship",
    body:
      "A pre-deploy check cancels the release if RLS is off on any table, a policy is open to " +
      "anonymous users, or a stranger's token can see a single row. Those are the failures " +
      "where everything still works, which is why they need checking.",
  },
  {
    title: "Exact arithmetic, explainable results",
    body:
      "Grade math uses exact fractions, so there's no float drift and ties always break the " +
      "same way. The student report says why each assignment counted, dropped, was excused " +
      "or is still ungraded.",
  },
  {
    title: "The front end can't drift from the API",
    body:
      "The dashboard's TypeScript types are generated from the API's OpenAPI schema, and CI " +
      "fails if they're stale. The dashboard has no copy of the grading rules; every percent " +
      "comes from the server.",
  },
];

const TESTS: [string, string][] = [
  ["Grade engine and statistics, incl. drop-lowest vs. brute force", "~400"],
  ["API: every resource, validation, cross-teacher isolation, CSV", "~170"],
  ["Real Postgres: RLS with deliberately unfiltered SQL", "12"],
  ["Dashboard units: cell parsing, keyboard, paste planning", "53"],
  ["End to end: a teacher's first day, in a real browser", "3"],
];

export default function AboutPage() {
  return (
    <article className="about">
      <header className="about-hero">
        <p className="about-kicker">Case study</p>
        <h1>A gradebook built by a teacher</h1>
        <p className="about-lede">
          Weighted categories, excused work, drop-lowest, assignment stats and CSV, behind an API
          where one teacher can never see another&apos;s students. I&apos;ve taught high school
          game design and computer science for five years, and math for two, keeping grades in
          Canvas and LiveGrades. The grading rules come from that.
        </p>
        <div className="about-actions">
          <Link href="/login" className="button primary">
            {demoEnabled ? "Try the live demo" : "Open the app"}
          </Link>
          <a href={`${API_URL}/docs`} className="button" target="_blank" rel="noreferrer">
            API docs
          </a>
          <a href={REPO} className="button" target="_blank" rel="noreferrer">
            Source on GitHub
          </a>
        </div>
        {demoEnabled && (
          <p className="muted about-note">
            The demo is a shared teacher account with 26 fictional students. No sign-up needed,
            and it resets nightly.
          </p>
        )}
        <ul className="about-chips" aria-label="Built with">
          {STACK.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      </header>

      <section>
        <h2>Why the rules work this way</h2>
        <p>
          Every grading rule answers a question a student or parent has asked me, or one I&apos;ve
          had to answer for myself.
        </p>
        <div className="about-rules">
          {RULES.map((rule) => (
            <div key={rule.title} className="about-rule">
              <h3>{rule.title}</h3>
              <p>{rule.body}</p>
            </div>
          ))}
        </div>
      </section>

      <section>
        <h2>The drop-lowest problem</h2>
        <p>
          Dropping the lowest <em>percentage</em> isn&apos;t what helps a student most when
          assignments have different point values:
        </p>
        <div className="about-table">
          <table className="plain">
            <thead>
              <tr>
                <th>Scores</th>
                <th>Drop the lowest % (9/20)</th>
                <th>Drop the 50/100 instead</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td>9/10, 50/100, 9/20</td>
                <td>
                  59/110 = <strong>53.6%</strong>
                </td>
                <td>
                  18/30 = <strong>60.0%</strong>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <p>
          Picking which assignments to keep so the ratio of points earned to points possible is
          as high as possible is a fractional programming problem. The engine solves it exactly
          with Dinkelbach&apos;s method, usually in two or three iterations, and a randomized
          test checks it against brute force over every subset.
        </p>
      </section>

      <section>
        <h2>Architecture</h2>
        <Diagram />
        <ul>
          <li>
            The browser signs in with Supabase, then talks only to the API with the
            teacher&apos;s token.
          </li>
          <li>
            The API verifies the token, then runs each database transaction as that teacher, so
            Row Level Security applies to every query.
          </li>
          <li>The grading engine is pure functions with no database, tested on its own.</li>
        </ul>
      </section>

      <section>
        <h2>Engineering decisions</h2>
        <div className="about-rules">
          {DECISIONS.map((decision) => (
            <div key={decision.title} className="about-rule">
              <h3>{decision.title}</h3>
              <p>{decision.body}</p>
            </div>
          ))}
        </div>
      </section>

      <section>
        <h2>Testing</h2>
        <div className="about-table">
          <table className="plain">
            <thead>
              <tr>
                <th>What</th>
                <th className="num">Tests</th>
              </tr>
            </thead>
            <tbody>
              {TESTS.map(([what, count]) => (
                <tr key={what}>
                  <td>{what}</td>
                  <td className="num">{count}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p>
          For the safety-critical code, such as ownership filters and CSV formula escaping, the
          code was broken on purpose to confirm the tests went red. CI runs everything on every
          push, including the Postgres tests and the browser test.
        </p>
      </section>

      <section>
        <h2>What&apos;s next</h2>
        <ul>
          <li>A grade history: who changed which grade, and when.</li>
          <li>Per-course letter scales; the engine already takes the scale as a parameter.</li>
          <li>Co-teachers, which RLS makes a policy change rather than a rewrite.</li>
        </ul>
        <p>
          The full write-up, with more on the math, the CSV handling and the deployment, is the{" "}
          <a href={`${REPO}/blob/main/docs/case-study.md`} target="_blank" rel="noreferrer">
            case study on GitHub
          </a>
          .
        </p>
      </section>
    </article>
  );
}

function Diagram() {
  return (
    <figure className="arch" aria-label="Architecture diagram">
      <div className="arch-row">
        <div className="arch-node">
          <strong>Teacher&apos;s browser</strong>
          <span>Next.js on Vercel</span>
        </div>
        <div className="arch-edge">
          <span>REST + bearer token</span>
        </div>
        <div className="arch-node arch-main">
          <strong>FastAPI</strong>
          <span>on Railway, grading engine</span>
        </div>
        <div className="arch-edge">
          <span>per transaction: run as the teacher</span>
        </div>
        <div className="arch-node">
          <strong>Postgres</strong>
          <span>Supabase, RLS on every table</span>
        </div>
      </div>
      <figcaption className="muted">
        Sign-in goes to Supabase Auth, and the API verifies each token against its published
        keys.
      </figcaption>
    </figure>
  );
}
