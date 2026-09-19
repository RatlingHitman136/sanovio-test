import { ApiError } from "@sanovio/api";
import { useMutation, useQueryClient } from "@tanstack/react-query";

/**
 * A change to an assessment. Afterwards, and after a version conflict too, the assessment is
 * reloaded, so the page always shows the hub's current state and version (§11).
 */
export function useAction<T>(assessmentId: string, run: (input: T) => Promise<unknown>) {
  const queries = useQueryClient();
  const refresh = () =>
    queries.invalidateQueries({ queryKey: ["hub", "assessment", assessmentId] });
  return useMutation({
    mutationFn: run,
    onSuccess: async () => {
      await refresh();
      await queries.invalidateQueries({ queryKey: ["hub", "assessments"] });
    },
    onError: async (error) => {
      if (error instanceof ApiError && error.code === "VERSION_CONFLICT") await refresh();
    },
  });
}
