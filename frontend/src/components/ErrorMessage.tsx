import { ApiError } from "../api/client";

/** An API error with the problems it lists (for example unresolved scenario references). */
export function ErrorMessage({ error }: { error: unknown }) {
  if (!error) return null;
  const message = error instanceof Error ? error.message : JSON.stringify(error);
  const problems = error instanceof ApiError ? error.problems : [];
  return (
    <div role="alert" className="error">
      <p>{message}</p>
      {problems.length > 0 && (
        <ul>
          {problems.map((p) => (
            <li key={p}>{p}</li>
          ))}
        </ul>
      )}
    </div>
  );
}
