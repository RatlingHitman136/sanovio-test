/** A refusal from either service, in the shape service-kit gives every error (§14). */
export class ApiError extends Error {
  readonly status: number;
  readonly code: string | undefined;
  readonly body: Record<string, unknown>;

  constructor(status: number, body: unknown) {
    const fields =
      typeof body === "object" && body !== null ? (body as Record<string, unknown>) : {};
    super(describe(fields.detail) ?? `request failed with ${status}`);
    this.name = "ApiError";
    this.status = status;
    this.code = typeof fields.code === "string" ? fields.code : undefined;
    this.body = fields;
  }
}

function describe(detail: unknown): string | undefined {
  if (typeof detail === "string") return detail;
  // FastAPI's validation errors: [{loc, msg}, …]
  if (Array.isArray(detail)) {
    return detail
      .map((item: { msg?: string; loc?: unknown[] }) =>
        [item.loc?.slice(1).join("."), item.msg].filter(Boolean).join(": "),
      )
      .join("; ");
  }
  return undefined;
}

type Outcome<T> = { data?: T; error?: unknown; response: Response };

/** The data of a successful call; anything else becomes an ApiError. */
export function unwrap<T>(outcome: Outcome<T>): T {
  if (!outcome.response.ok) throw new ApiError(outcome.response.status, outcome.error);
  return outcome.data as T;
}
