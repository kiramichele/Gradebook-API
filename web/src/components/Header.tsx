"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";

import { supabase } from "@/lib/supabase";

import { useAuth } from "./AuthProvider";

export function Header() {
  const { session } = useAuth();
  const router = useRouter();

  async function signOut() {
    await supabase().auth.signOut();
    router.replace("/login");
  }

  return (
    <header className="topbar">
      <Link href="/" className="brand">
        Gradebook
      </Link>
      {session && (
        <div className="topbar-user">
          <span className="muted topbar-email">{session.user.email}</span>
          <button type="button" className="link" onClick={signOut}>
            Sign out
          </button>
        </div>
      )}
    </header>
  );
}
