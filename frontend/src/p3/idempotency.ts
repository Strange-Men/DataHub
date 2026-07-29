const SAFE_SCOPE = /[^a-z0-9_-]+/gi;

export function createP3IdempotencyKey(scope: string): string {
  const normalizedScope = scope.trim().replace(SAFE_SCOPE, "-").replace(/^-+|-+$/g, "");
  const prefix = normalizedScope || "operation";
  return `p3-ui-${prefix}-${crypto.randomUUID()}`;
}
