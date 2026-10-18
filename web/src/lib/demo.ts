// The public demo account. Both values are set in Vercel only when a demo
// has been seeded (see docs/deploy.md); without them the demo button is hidden.
// The password is public on purpose: the account holds only fictional data,
// and a nightly job restores both the data and the password.
export const DEMO_EMAIL = process.env.NEXT_PUBLIC_DEMO_EMAIL?.trim() ?? "";
export const DEMO_PASSWORD = process.env.NEXT_PUBLIC_DEMO_PASSWORD ?? "";

export const demoEnabled = Boolean(DEMO_EMAIL && DEMO_PASSWORD);

export function isDemoUser(email: string | undefined): boolean {
  return demoEnabled && email?.toLowerCase() === DEMO_EMAIL.toLowerCase();
}
