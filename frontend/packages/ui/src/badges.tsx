/** Colour-coded labels for the domain's states, so a table can be read at a glance. */
import { cn } from "./cn";

type Tone = "neutral" | "info" | "good" | "warn" | "bad";

const tones: Record<Tone, string> = {
  neutral: "bg-neutral-100 text-neutral-700",
  info: "bg-blue-50 text-blue-700",
  good: "bg-green-50 text-green-700",
  warn: "bg-amber-50 text-amber-800",
  bad: "bg-red-50 text-red-700",
};

export function Badge({ tone = "neutral", children }: { tone?: Tone; children: string }) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium whitespace-nowrap",
        tones[tone],
      )}
    >
      {children}
    </span>
  );
}

function label(code: string): string {
  return code.replaceAll("_", " ").toLowerCase();
}

const STATUS: Record<string, Tone> = {
  ASSESSING: "info",
  NEEDS_QUESTION_REVIEW: "warn",
  AWAITING_ANSWERS: "info",
  PROPOSED_RESOLUTION: "good",
  NEEDS_MANUAL_DECISION: "warn",
  FAILED: "bad",
  RESOLVED: "neutral",
  CANCELLED: "neutral",
};

export function StatusBadge({ status }: { status: string }) {
  return <Badge tone={STATUS[status] ?? "neutral"}>{label(status)}</Badge>;
}

const VERDICT: Record<string, Tone> = {
  EQUIVALENT: "good",
  EQUIVALENT_WITH_DEVIATIONS: "warn",
  NOT_EQUIVALENT: "bad",
  INSUFFICIENT_DATA: "info",
  UNDETERMINED: "neutral",
};

export function VerdictBadge({ verdict }: { verdict: string | null | undefined }) {
  if (!verdict) return <span className="text-neutral-400">–</span>;
  return <Badge tone={VERDICT[verdict] ?? "neutral"}>{label(verdict)}</Badge>;
}

const JUDGMENT: Record<string, Tone> = {
  MATCH: "good",
  ACCEPTABLE_DEVIATION: "warn",
  MISMATCH: "bad",
  UNKNOWN: "info",
  UNAVAILABLE: "neutral",
  INFO: "neutral",
  NEEDS_JUDGE: "info",
};

export function JudgmentBadge({ status }: { status: string }) {
  return <Badge tone={JUDGMENT[status] ?? "neutral"}>{label(status)}</Badge>;
}

const CRITICALITY: Record<string, Tone> = { critical: "bad", major: "warn", minor: "neutral" };

export function CriticalityBadge({ criticality }: { criticality: string }) {
  return <Badge tone={CRITICALITY[criticality] ?? "neutral"}>{criticality}</Badge>;
}
