// Stand in for Supabase Auth: answer the browser's sign-in request with a
// session whose access token is a real HS256 JWT. The API verifies it with
// the same secret, so everything past the sign-in screen is the real stack.
import { createHmac, randomUUID } from "node:crypto";

import type { Page } from "@playwright/test";

export const SUPABASE_URL = "http://supabase.test";
export const JWT_SECRET = "e2e-secret-that-is-at-least-32-bytes";

function base64url(data: string | Buffer): string {
  return Buffer.from(data).toString("base64url");
}

export function signToken(claims: Record<string, unknown>): string {
  const header = base64url(JSON.stringify({ alg: "HS256", typ: "JWT" }));
  const payload = base64url(JSON.stringify(claims));
  const signature = createHmac("sha256", JWT_SECRET).update(`${header}.${payload}`).digest();
  return `${header}.${payload}.${base64url(signature)}`;
}

export type TestUser = { id: string; email: string; name: string };

export function newUser(name: string): TestUser {
  const id = randomUUID();
  return { id, name, email: `${name.toLowerCase().replace(/\W+/g, ".")}.${id.slice(0, 6)}@example.edu` };
}

/** Route Supabase Auth calls so that signing in with any password logs in as `user`. */
export async function mockSupabaseAuth(page: Page, user: TestUser): Promise<void> {
  await page.route(`${SUPABASE_URL}/auth/v1/**`, async (route) => {
    const url = new URL(route.request().url());
    if (url.pathname.endsWith("/logout")) {
      return route.fulfill({ status: 204 });
    }
    if (url.pathname.endsWith("/token")) {
      const now = Math.floor(Date.now() / 1000);
      const supabaseUser = {
        id: user.id,
        aud: "authenticated",
        role: "authenticated",
        email: user.email,
        user_metadata: { name: user.name },
        app_metadata: { provider: "email" },
        created_at: new Date().toISOString(),
      };
      const accessToken = signToken({
        sub: user.id,
        aud: "authenticated",
        role: "authenticated",
        iss: `${SUPABASE_URL}/auth/v1`,
        email: user.email,
        user_metadata: { name: user.name },
        iat: now,
        exp: now + 3600,
      });
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          access_token: accessToken,
          token_type: "bearer",
          expires_in: 3600,
          expires_at: now + 3600,
          refresh_token: randomUUID(),
          user: supabaseUser,
        }),
      });
    }
    return route.fulfill({ status: 404, body: "{}" });
  });
}
