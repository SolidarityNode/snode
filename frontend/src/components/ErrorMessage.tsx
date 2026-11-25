import { ApiError } from "../api/client";
import { useT } from "../i18n/context";
import { serverText } from "../i18n/server";

/** An API error with the problems it lists, translated where the server text has a template. */
export function ErrorMessage({ error }: { error: unknown }) {
  const { t } = useT();
  if (!error) return null;
  const message = error instanceof Error ? error.message : JSON.stringify(error);
  const problems = error instanceof ApiError ? error.problems : [];
  return (
    <div role="alert" className="error">
      <p>{serverText(t, message)}</p>
      {problems.length > 0 && (
        <ul>
          {problems.map((p) => (
            <li key={p}>{serverText(t, p)}</li>
          ))}
        </ul>
      )}
    </div>
  );
}
