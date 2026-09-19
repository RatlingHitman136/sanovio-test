/** How refusals and confirmations reach the user. */
import { ApiError } from "@sanovio/api";
import { Dialog as RadixDialog } from "radix-ui";
import type { ReactNode } from "react";

import { Button } from "./primitives";

export function describeError(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 409 && error.code === "VERSION_CONFLICT") {
      return "Someone changed this in the meantime. The page has been refreshed; try again.";
    }
    return error.code ? `${error.message} (${error.code})` : error.message;
  }
  return error instanceof Error ? error.message : "Something went wrong.";
}

export function ErrorMessage({ error }: { error: unknown }) {
  if (!error) return null;
  return (
    <p role="alert" className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-700">
      {describeError(error)}
    </p>
  );
}

export function Notice({ children }: { children: ReactNode }) {
  return <p className="rounded-md bg-blue-50 px-3 py-2 text-sm text-blue-800">{children}</p>;
}

interface DialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  children: ReactNode;
  footer?: ReactNode;
}

export function Dialog({ open, onOpenChange, title, children, footer }: DialogProps) {
  return (
    <RadixDialog.Root open={open} onOpenChange={onOpenChange}>
      <RadixDialog.Portal>
        <RadixDialog.Overlay className="fixed inset-0 bg-black/30" />
        <RadixDialog.Content className="fixed top-1/2 left-1/2 w-[min(640px,92vw)] -translate-x-1/2 -translate-y-1/2 rounded-lg bg-white p-5 shadow-lg">
          <RadixDialog.Title className="mb-3 text-lg font-semibold">{title}</RadixDialog.Title>
          <RadixDialog.Description className="sr-only">{title}</RadixDialog.Description>
          <div className="max-h-[65vh] overflow-y-auto">{children}</div>
          <div className="mt-4 flex justify-end gap-2">
            <RadixDialog.Close asChild>
              <Button variant="secondary">Close</Button>
            </RadixDialog.Close>
            {footer}
          </div>
        </RadixDialog.Content>
      </RadixDialog.Portal>
    </RadixDialog.Root>
  );
}
