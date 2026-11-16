import { APP_VERSION } from "./FeedbackDialog";

export function Footer({ onFeedback }: { onFeedback: () => void }) {
  return (
    <footer className="flex flex-col gap-3 border-t border-line pt-6 text-muted sm:flex-row sm:items-center sm:justify-between">
      <div className="flex flex-col gap-1">
        <p>Listening uses your browser&apos;s speech service, so it needs internet.</p>
        <p className="text-sm">
          Built by{" "}
          <a
            href="https://www.linkedin.com/in/julius-ogunniyi-97884b199/"
            target="_blank"
            rel="noopener noreferrer"
            className="font-semibold text-navy underline-offset-4 hover:text-brand hover:underline"
          >
            Julius Ogunniyi
          </a>
          <span className="ml-2 text-xs text-muted/70">{APP_VERSION}</span>
        </p>
      </div>
      <button type="button" onClick={onFeedback} className="self-start font-semibold text-navy underline underline-offset-4 hover:text-brand sm:self-auto">
        Send feedback
      </button>
    </footer>
  );
}
