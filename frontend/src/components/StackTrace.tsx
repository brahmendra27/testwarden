export function StackTrace({ trace }: { trace: string }) {
  return (
    <pre className="max-h-96 overflow-auto rounded-lg bg-zinc-900 p-4 text-xs leading-5 text-zinc-300">
      {trace.split("\n").map((line, index) => {
        const isError = line.startsWith("E ") || line.startsWith("E\t") || line.trim().startsWith("E   ");
        const isPointer = line.startsWith(">");
        return (
          <div
            key={index}
            className={isError ? "text-red-400" : isPointer ? "text-amber-300" : undefined}
          >
            {line || " "}
          </div>
        );
      })}
    </pre>
  );
}
