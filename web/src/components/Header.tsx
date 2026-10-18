"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { API_URL } from "@/lib/api";
import { isDemoUser } from "@/lib/demo";
import { supabase } from "@/lib/supabase";

import { useAuth } from "./AuthProvider";

export function Header() {
  const { session } = useAuth();
  const router = useRouter();
  const [copied, setCopied] = useState(false);

  async function signOut() {
    await supabase().auth.signOut();
    router.replace("/login");
  }

  // For the Authorize box on the API's /docs page.
  async function copyToken() {
    if (!session) return;
    await navigator.clipboard.writeText(session.access_token);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  return (
    <>
      <header className="topbar">
        <Link href="/" className="brand">
          Gradebook
        </Link>
        <div className="topbar-user">
          <a href={`${API_URL}/docs`} target="_blank" rel="noreferrer">
            API docs
          </a>
          {session && (
            <>
              <button type="button" className="link" onClick={copyToken}>
                {copied ? "Token copied" : "API token"}
              </button>
              <span className="muted topbar-email">{session.user.email}</span>
              <button type="button" className="link" onClick={signOut}>
                Sign out
              </button>
            </>
          )}
        </div>
      </header>
      {session && isDemoUser(session.user.email) && (
        <p className="demo-banner">
          You&apos;re in the shared demo. The students are fictional, and the data resets nightly,
          so edit freely.
        </p>
      )}
    </>
  );
}
