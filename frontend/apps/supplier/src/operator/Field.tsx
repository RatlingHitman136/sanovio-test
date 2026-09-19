import { Label } from "@sanovio/ui";
import type { ReactNode } from "react";

/** A labelled form control in the operator's dialogs. */
export function Field({ label, id, children }: { label: string; id: string; children: ReactNode }) {
  return (
    <div className="space-y-1">
      <Label htmlFor={id}>{label}</Label>
      {children}
    </div>
  );
}
