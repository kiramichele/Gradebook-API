# Deploying

The API runs on **Railway**, the dashboard on **Vercel**, and the database and
auth on **Supabase**. The steps go in this order because each service needs a
URL from the one before it. Budget about 30 minutes the first time.

```
Supabase (Postgres + Auth)  <──  Railway (FastAPI, this repo's root)  <──  Vercel (Next.js, web/)
```

## 1. Supabase

1. Create a project at [supabase.com](https://supabase.com). Note the database
   password you choose.
2. **Apply the schema.** Open **SQL Editor**, paste the contents of
   [`supabase/migrations/20261017000000_init.sql`](../supabase/migrations/20261017000000_init.sql)
   and run it. Or, with the Supabase CLI:
   ```bash
   supabase init            # once; keeps the existing supabase/migrations
   supabase link --project-ref <project-ref>
   supabase db push
   ```
3. **Collect these values:**

   | What | Where in the dashboard | Used by |
   |---|---|---|
   | Project URL (`https://<ref>.supabase.co`) | Project Settings → API | Railway, Vercel, seeding |
   | Publishable (or legacy `anon`) key | Project Settings → API Keys | Vercel, seeding |
   | Secret (or legacy `service_role`) key | Project Settings → API Keys | seeding only, never deployed |
   | **Session pooler** connection string | **Connect** button → Session pooler | Railway |

   Use the **session pooler** string (port 5432, user `postgres.<ref>`). It
   works over IPv4 and suits a long-running server. The direct connection is
   IPv6-only, and the transaction pooler (port 6543) is meant for serverless
   functions. The API turns off prepared statements, so either pooler mode works.

   Token signing: new projects sign tokens with asymmetric keys, which the API
   fetches from the project's JWKS automatically. If your project still uses
   the legacy shared JWT secret, copy it from Project Settings → JWT Keys and
   set `SUPABASE_JWT_SECRET` in step 2.

## 2. Railway (API)

1. **New Project → Deploy from GitHub repo**, and pick this repository. Railway
   reads [`railway.json`](../railway.json) and builds the
   [`Dockerfile`](../Dockerfile) at the repo root.
2. **Variables** for the service:

   | Variable | Value |
   |---|---|
   | `DATABASE_URL` | the session pooler string, with the scheme changed to `postgresql+psycopg://` and your password filled in |
   | `SUPABASE_URL` | `https://<ref>.supabase.co` |
   | `CORS_ORIGINS` | your Vercel URL from step 3. Put a placeholder for now; the first deploy will fail its check until it's set (that's intended) |
   | `SUPABASE_JWT_SECRET` | only for legacy-secret projects |
   | `WEB_CONCURRENCY` | optional, worker processes (default 2) |

3. **Settings → Networking → Generate Domain** to get the API's public URL.
4. Every deploy runs [`scripts/check_deploy.py`](../scripts/check_deploy.py)
   first and is **cancelled if any check fails**. The output in the deploy log
   should end with `11/11 checks passed`:

   ```
   [ok  ] DATABASE_URL is Postgres
   [ok  ] SUPABASE_URL is set
   [ok  ] CORS_ORIGINS includes the deployed dashboard
   [ok  ] JWKS reachable
   [ok  ] Database reachable
   [ok  ] Migration applied
   [ok  ] RLS enabled on every table
   [ok  ] Policies apply only to signed-in users
   [ok  ] authenticated role does not bypass RLS
   [ok  ] API user can act as authenticated
   [ok  ] A stranger sees no rows
   ```

   A failure names the fix, e.g. *missing tables: …; run supabase/migrations*
   or *postgres.xyz cannot SET ROLE authenticated; connect as the postgres user*.

5. Check `https://<api-domain>/health` returns `{"status":"ok"}` and
   `https://<api-domain>/docs` shows the API docs.

## 3. Vercel (dashboard)

1. **Add New → Project**, import this repository, and set **Root Directory**
   to `web`. Vercel detects Next.js.
2. **Environment Variables:**

   | Variable | Value |
   |---|---|
   | `NEXT_PUBLIC_SUPABASE_URL` | `https://<ref>.supabase.co` |
   | `NEXT_PUBLIC_SUPABASE_ANON_KEY` | the publishable (or `anon`) key |
   | `NEXT_PUBLIC_API_URL` | `https://<api-domain>` from step 2 |

   These are build-time values: after changing one, redeploy.
3. Deploy, and note the URL (e.g. `https://gradebook-yourname.vercel.app`).

## 4. Connect them

1. **Railway:** set `CORS_ORIGINS` to the Vercel URL (comma-separate several,
   e.g. a custom domain too). Railway redeploys, and the check should now pass.
2. **Supabase → Authentication → URL Configuration:** set **Site URL** to the
   Vercel URL and add `https://<vercel-url>/**` to **Redirect URLs**, so
   sign-up confirmation emails link back to the dashboard.

## 5. Seed the demo

From your machine, with the repo's dev install (`pip install -e ".[dev]"`):

```bash
export SUPABASE_URL=https://<ref>.supabase.co
export SUPABASE_ANON_KEY=<publishable key>
export SUPABASE_SERVICE_ROLE_KEY=<secret key>     # only needed with --create-user

python scripts/seed_demo.py --api-url https://<api-domain> \
  --email demo@<your-domain> --password '<a long password>' --create-user
```

This creates a confirmed demo teacher and, **through the deployed API**,
two courses (AP Chemistry, Algebra II), 26 fictional students imported by
CSV, weighted categories with drop-lowest, and grades with some missing,
excused and late work. Assignments due after today stay ungraded. The data is
the same on every run. Re-run with `--reset` to restore the demo after
visitors have edited it.

Seeding uses the same token and endpoints as the dashboard, so a successful
run also proves the deployment works end to end.

## 6. Smoke test

- [ ] Sign in to the dashboard as the demo teacher, and see both courses.
- [ ] Open AP Chemistry: the grid shows 22 students, with missing (red),
      excused (gray), late (L) and dropped (struck through) cells.
- [ ] Type a grade and see the course percent update. Reload, and the change is kept.
- [ ] Click an assignment header and see stats and a histogram.
- [ ] Export CSV downloads `ap-chemistry-fall-2026.csv`.
- [ ] Sign up as a second teacher in a private window and see **no** courses.

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| Deploy cancelled at pre-deploy | Read the `[FAIL]` line in the deploy log; it names the fix |
| Dashboard says "Can't reach the API" | `NEXT_PUBLIC_API_URL` is wrong, or the Vercel build predates it (redeploy) |
| Browser console shows a CORS error | `CORS_ORIGINS` on Railway doesn't exactly match the Vercel origin (scheme, no trailing slash) |
| Every request is 401 | Project uses the legacy JWT secret: set `SUPABASE_JWT_SECRET` |
| Sign-up email links to localhost | Supabase Site URL not updated (step 4) |
