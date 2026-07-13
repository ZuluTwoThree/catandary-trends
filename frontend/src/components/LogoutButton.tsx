"use client";

export default function LogoutButton() {
  async function logout() {
    const res = await fetch("/api/auth/logout", { method: "POST" });
    const data = await res.json().catch(() => ({}));
    window.location.href = data.redirect || "/trends";
  }
  return (
    <button
      onClick={logout}
      className="rounded-lg border border-current/20 px-3 py-1.5 text-sm hover:bg-current/5"
    >
      Sign out
    </button>
  );
}
