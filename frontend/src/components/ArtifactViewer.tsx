import type { ArtifactInfo } from "../api/types";

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function ArtifactViewer({ artifacts }: { artifacts: ArtifactInfo[] }) {
  if (!artifacts.length) {
    return <p className="text-sm text-zinc-500">No artifacts captured for this attempt.</p>;
  }
  return (
    <div className="space-y-4">
      {artifacts.map((artifact) => (
        <div key={artifact.id} className="rounded-lg border border-zinc-800 p-3">
          <div className="mb-2 flex items-center gap-3 text-sm">
            <span className="rounded bg-zinc-800 px-2 py-0.5 text-xs uppercase text-zinc-400">
              {artifact.kind}
            </span>
            <span className="text-zinc-300">{artifact.file_name}</span>
            <span className="text-zinc-500">{formatBytes(artifact.size_bytes)}</span>
            <a
              href={artifact.url}
              download={artifact.file_name}
              className="ml-auto text-sky-400 hover:underline"
            >
              download
            </a>
          </div>
          {artifact.content_type.startsWith("image/") && (
            <img
              src={artifact.url}
              alt={artifact.file_name}
              className="max-h-80 rounded border border-zinc-800"
            />
          )}
          {artifact.content_type.startsWith("video/") && (
            <video src={artifact.url} controls className="max-h-80 rounded" />
          )}
          {artifact.kind === "trace" && (
            <p className="text-xs text-zinc-500">
              Playwright trace — download and open at{" "}
              <a
                href="https://trace.playwright.dev"
                target="_blank"
                rel="noreferrer"
                className="text-sky-400 hover:underline"
              >
                trace.playwright.dev
              </a>
            </p>
          )}
        </div>
      ))}
    </div>
  );
}
