import { useState, type SyntheticEvent } from "react";
import { useLocation, useNavigate } from "react-router";

import { ApiError } from "../api/client";
import { useSession } from "../app/session";
import { ErrorMessage } from "../components/ErrorMessage";
import { useT } from "../i18n/context";

export function LoginPage() {
  const { t } = useT();
  const { login } = useSession();
  const navigate = useNavigate();
  const location = useLocation();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: SyntheticEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await login(username, password);
      const from = (location.state as { from?: string } | null)?.from ?? "/";
      void navigate(from, { replace: true });
    } catch (e) {
      // The same generic messages whether or not the user exists (ADR 0015).
      const throttled = e instanceof ApiError && e.status === 429;
      setError(new Error(t(throttled ? "login.throttled" : "login.failed")));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section aria-labelledby="login-title" className="narrow">
      <h2 id="login-title">{t("login.title")}</h2>
      <form onSubmit={(e) => void submit(e)}>
        <label>
          {t("login.username")}
          <input
            name="username"
            autoComplete="username"
            value={username}
            onChange={(e) => {
              setUsername(e.target.value);
            }}
            required
          />
        </label>
        <label>
          {t("login.password")}
          <input
            name="password"
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(e) => {
              setPassword(e.target.value);
            }}
            required
          />
        </label>
        <button type="submit" disabled={busy}>
          {t("login.submit")}
        </button>
      </form>
      <ErrorMessage error={error} />
    </section>
  );
}
