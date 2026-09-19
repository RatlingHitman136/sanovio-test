import { Card } from "@sanovio/ui";

/**
 * Exactly what the node issued for the hub (§16): shown before it is used, so the purchaser
 * can see that no name, price or internal number leaves the hospital.
 */
export function RequirementPanel({ requirement }: { requirement: unknown }) {
  return (
    <Card className="bg-neutral-50">
      <details>
        <summary className="cursor-pointer text-sm font-medium text-neutral-800">
          What leaves the hospital
        </summary>
        <pre className="mt-3 max-h-80 overflow-auto rounded bg-white p-3 text-xs text-neutral-700">
          {JSON.stringify(requirement, null, 2)}
        </pre>
      </details>
    </Card>
  );
}
