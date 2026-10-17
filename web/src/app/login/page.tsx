"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState, type FormEvent } from "react";

import { useAuth } from "@/components/AuthProvider";
import { supabase } from "@/lib/supabase";

function nextPath(): string {
  const next = new URLSearchParams(window.location.search).get("next");
  // Only same-site paths, so the login page can't be used as an open redirect.
  return next && next.startsWith("/") && !next.startsWith("//") ? next : "/";
}

export default function LoginPage() {
  const { session } = useAuth();
  const router = useRouter();
  const [mode, setMode] = useState<"sign-in" | "sign-up">("sign-in");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ kind: "error" | "info"; text: string }>();

  useEffect(() => {
    if (session) router.replace(nextPath());
  }, [session, router]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setMessage(undefined);
    const auth = supabase().auth;
    const { data, error } =
      mode === "sign-in"
        ? await auth.signInWithPassword({ email, password })
        : await auth.signUp({
            email,
            password,
            // The confirmation link brings the teacher back to this deployment.
            options: { data: { name }, emailRedirectTo: `${window.location.origin}/login` },
          });
    setBusy(false);
    if (error) {
      setMessage({ kind: "error", text: error.message });
    } else if (mode === "sign-up" && !data.session) {
      setMessage({ kind: "info", text: "Check your email to confirm your account, then sign in." });
    }
  }

  return (
    <div className="auth-card card">
      <h1>{mode === "sign-in" ? "Sign in" : "Create your account"}</h1>
      <form onSubmit={submit} className="stack">
        {mode === "sign-up" && (
          <label>
            Name
            <input value={name} onChange={(e) => setName(e.target.value)} autoComplete="name" />
          </label>
        )}
        <label>
          Email
          <input
            type="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            autoComplete="email"
          />
        </label>
        <label>
          Password
          <input
            type="password"
            required
            minLength={6}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete={mode === "sign-in" ? "current-password" : "new-password"}
          />
        </label>
        {message && (
          <p className={message.kind === "error" ? "error" : "notice"} role="alert">
            {message.text}
          </p>
        )}
        <button type="submit" className="primary" disabled={busy}>
          {busy ? "…" : mode === "sign-in" ? "Sign in" : "Create account"}
        </button>
      </form>
      <p className="muted">
        {mode === "sign-in" ? "New here? " : "Already have an account? "}
        <button
          type="button"
          className="link"
          onClick={() => {
            setMode(mode === "sign-in" ? "sign-up" : "sign-in");
            setMessage(undefined);
          }}
        >
          {mode === "sign-in" ? "Create an account" : "Sign in"}
        </button>
      </p>
    </div>
  );
}
