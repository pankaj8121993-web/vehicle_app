import { AlertTriangle, FileQuestion, Loader2, LockKeyhole, SearchX, WifiOff } from "lucide-react";
import { Button } from "@/components/ui/button";

const ICONS = { empty: FileQuestion, error: AlertTriangle, forbidden: LockKeyhole, network: WifiOff, "no-results": SearchX };

export const PageLoading = ({ label = "Loading…" }) => (
  <div className="flex min-h-48 items-center justify-center gap-3 text-sm text-slate-500" role="status" aria-live="polite">
    <Loader2 className="h-5 w-5 animate-spin" aria-hidden="true" />
    <span>{label}</span>
  </div>
);

export const PageState = ({ kind = "empty", title, description, actionLabel, onAction, children }) => {
  const Icon = ICONS[kind] || FileQuestion;
  return (
    <section className="mx-auto flex min-h-64 max-w-xl flex-col items-center justify-center px-4 py-10 text-center" role={kind === "error" || kind === "network" ? "alert" : "status"}>
      <span className="mb-4 grid h-12 w-12 place-items-center rounded-full bg-slate-100 text-slate-600">
        <Icon className="h-6 w-6" aria-hidden="true" />
      </span>
      <h1 className="font-heading text-xl font-bold text-slate-900">{title}</h1>
      {description && <p className="mt-2 text-sm leading-6 text-slate-600">{description}</p>}
      {children}
      {actionLabel && onAction && <Button className="mt-5" onClick={onAction}>{actionLabel}</Button>}
    </section>
  );
};
