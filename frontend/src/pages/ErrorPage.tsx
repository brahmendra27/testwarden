import { Link, isRouteErrorResponse, useRouteError } from "react-router-dom";

export function ErrorPage() {
  const error = useRouteError();
  const is404 = isRouteErrorResponse(error) && error.status === 404;
  return (
    <div className="flex min-h-screen items-center justify-center p-6">
      <div className="card max-w-md p-8 text-center">
        <div className="grad-text mb-2 text-5xl font-bold">{is404 ? "404" : "Oops"}</div>
        <p className="mb-6 text-sm text-zinc-400">
          {is404
            ? "That page doesn't exist — the link may be outdated."
            : "Something went wrong rendering this page."}
        </p>
        <Link to="/" className="btn-grad inline-block">
          ← Back to projects
        </Link>
      </div>
    </div>
  );
}
