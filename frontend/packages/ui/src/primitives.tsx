/** Small building blocks in the shadcn/ui style (Radix + Tailwind), shared by both apps. */
import { cva, type VariantProps } from "class-variance-authority";
import type { ComponentProps, ReactNode } from "react";

import { cn } from "./cn";

const button = cva(
  "inline-flex items-center justify-center gap-2 rounded-md text-sm font-medium transition-colors " +
    "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent " +
    "disabled:pointer-events-none disabled:opacity-50",
  {
    variants: {
      variant: {
        primary: "bg-accent text-accent-foreground hover:bg-accent/90",
        secondary: "border border-neutral-300 bg-white text-neutral-900 hover:bg-neutral-50",
        ghost: "text-neutral-700 hover:bg-neutral-100",
        danger: "bg-red-600 text-white hover:bg-red-700",
      },
      size: { sm: "h-8 px-3", md: "h-9 px-4", lg: "h-10 px-5" },
    },
    defaultVariants: { variant: "primary", size: "md" },
  },
);

export function Button({
  className,
  variant,
  size,
  type = "button",
  ...props
}: ComponentProps<"button"> & VariantProps<typeof button>) {
  return <button type={type} className={cn(button({ variant, size }), className)} {...props} />;
}

const field =
  "block w-full rounded-md border border-neutral-300 bg-white px-3 py-1.5 text-sm " +
  "focus:border-accent focus:outline-none focus:ring-1 focus:ring-accent disabled:bg-neutral-100";

export function Input({ className, ...props }: ComponentProps<"input">) {
  return <input className={cn(field, "h-9", className)} {...props} />;
}

export function Textarea({ className, ...props }: ComponentProps<"textarea">) {
  return <textarea className={cn(field, "min-h-16", className)} {...props} />;
}

export function Select({ className, ...props }: ComponentProps<"select">) {
  return <select className={cn(field, "h-9", className)} {...props} />;
}

export function Label({ className, ...props }: ComponentProps<"label">) {
  return <label className={cn("text-sm font-medium text-neutral-800", className)} {...props} />;
}

export function Card({ className, ...props }: ComponentProps<"section">) {
  return (
    <section
      className={cn("rounded-lg border border-neutral-200 bg-white p-4 shadow-xs", className)}
      {...props}
    />
  );
}

export function CardTitle({ className, ...props }: ComponentProps<"h2">) {
  return (
    <h2 className={cn("mb-3 text-base font-semibold text-neutral-900", className)} {...props} />
  );
}

export function Table({ className, ...props }: ComponentProps<"table">) {
  return (
    <div className="overflow-x-auto">
      <table className={cn("w-full border-collapse text-left text-sm", className)} {...props} />
    </div>
  );
}

export function Th({ className, ...props }: ComponentProps<"th">) {
  return (
    <th
      className={cn(
        "border-b border-neutral-200 px-3 py-2 text-xs font-semibold uppercase tracking-wide text-neutral-500",
        className,
      )}
      {...props}
    />
  );
}

export function Td({ className, ...props }: ComponentProps<"td">) {
  return (
    <td className={cn("border-b border-neutral-100 px-3 py-2 align-top", className)} {...props} />
  );
}

export function PageHeader({ title, children }: { title: ReactNode; children?: ReactNode }) {
  return (
    <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
      <h1 className="text-xl font-semibold text-neutral-900">{title}</h1>
      {children && <div className="flex items-center gap-2">{children}</div>}
    </div>
  );
}

export function Spinner({ label = "Loading…" }: { label?: string }) {
  return (
    <p role="status" className="text-sm text-neutral-500">
      {label}
    </p>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return <p className="py-6 text-center text-sm text-neutral-500">{children}</p>;
}
