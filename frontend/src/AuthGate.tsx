import { useEffect, useState } from "react";

interface AuthStatus {
  required: boolean;
  authenticated: boolean;
}

function LoginScreen({ onSuccess }: { onSuccess: () => void }) {
  const [token, setToken] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const response = await fetch("/api/v1/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ token }),
      });
      if (!response.ok) {
        setError("Invalid access token");
        return;
      }
      onSuccess();
    } catch {
      setError("Could not reach the server");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center p-6">
      <form onSubmit={submit} className="card w-full max-w-sm p-8 text-center">
        <div className="mb-6 flex items-center justify-center gap-2.5">
          <span className="glow-dot" />
          <span className="grad-text text-2xl font-bold" style={{ fontFamily: "Plus Jakarta Sans" }}>
            FlakeLens
          </span>
        </div>
        <p className="mb-4 text-sm text-zinc-400">Enter the access token to continue.</p>
        <input
          type="password"
          value={token}
          onChange={(e) => setToken(e.target.value)}
          placeholder="Access token"
          className="field mb-3 w-full text-center"
          autoFocus
        />
        <button type="submit" disabled={!token || busy} className="btn-grad w-full">
          {busy ? "Checking…" : "Sign in"}
        </button>
        {error && <p className="mt-3 text-xs text-red-400">{error}</p>}
      </form>
    </div>
  );
}

export function AuthGate({ children }: { children: React.ReactNode }) {
  const [status, setStatus] = useState<AuthStatus | null>(null);

  const refresh = () =>
    fetch("/api/v1/auth/status")
      .then((r) => r.json())
      .then(setStatus)
      .catch(() => setStatus({ required: false, authenticated: true }));

  useEffect(() => {
    refresh();
  }, []);

  if (status === null) {
    return <div className="flex min-h-screen items-center justify-center text-zinc-500">Loading…</div>;
  }
  if (status.required && !status.authenticated) {
    return <LoginScreen onSuccess={refresh} />;
  }
  return <>{children}</>;
}
