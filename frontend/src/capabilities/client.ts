import { apiPath, publicApiFetch } from "../api";
import type {
  CapabilitiesResponse,
  CapabilityApiStatus,
  CapabilityAuthority,
  CapabilityEnvironment,
  InfrastructureAvailability,
  ModuleCapability,
  StorageAvailability,
} from "./types";

const ENVIRONMENTS: ReadonlySet<CapabilityEnvironment> = new Set([
  "local",
  "test",
  "staging",
  "production",
]);
const AUTHORITIES: ReadonlySet<CapabilityAuthority> = new Set([
  "local_docker",
  "deployed_environment",
]);
const MODULE_STATUSES: ReadonlySet<Exclude<CapabilityApiStatus, "planned">> = new Set([
  "available",
  "local_only",
  "degraded",
  "unavailable",
]);
const INFRASTRUCTURE_AVAILABILITY: ReadonlySet<InfrastructureAvailability> = new Set([
  "available",
  "unavailable",
]);
const STORAGE_AVAILABILITY: ReadonlySet<StorageAvailability> = new Set([
  "available",
  "unavailable",
  "local_only",
]);

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function hasStringReasons(value: Record<string, unknown>): value is Record<string, unknown> & {
  reason_codes: string[];
} {
  return Array.isArray(value.reason_codes) && value.reason_codes.every((code) => typeof code === "string");
}

function isModuleCapability(
  value: unknown,
): value is ModuleCapability<Exclude<CapabilityApiStatus, "planned">> {
  return isRecord(value)
    && MODULE_STATUSES.has(value.status as Exclude<CapabilityApiStatus, "planned">)
    && hasStringReasons(value);
}

function isPlannedModule(value: unknown): value is ModuleCapability<"planned"> {
  return isRecord(value) && value.status === "planned" && hasStringReasons(value);
}

function isCapabilitiesResponse(value: unknown): value is CapabilitiesResponse {
  if (!isRecord(value) || !isRecord(value.auth) || !isRecord(value.infrastructure)
    || !isRecord(value.modules) || !isRecord(value.features)) {
    return false;
  }

  return ENVIRONMENTS.has(value.environment as CapabilityEnvironment)
    && AUTHORITIES.has(value.authority as CapabilityAuthority)
    && (value.auth.mode === "disabled" || value.auth.mode === "token")
    && typeof value.auth.safe_for_environment === "boolean"
    && INFRASTRUCTURE_AVAILABILITY.has(
      value.infrastructure.database as InfrastructureAvailability,
    )
    && INFRASTRUCTURE_AVAILABILITY.has(
      value.infrastructure.pgvector as InfrastructureAvailability,
    )
    && STORAGE_AVAILABILITY.has(value.infrastructure.asset_storage as StorageAvailability)
    && STORAGE_AVAILABILITY.has(value.infrastructure.export_storage as StorageAvailability)
    && isModuleCapability(value.modules.p1)
    && isModuleCapability(value.modules.p2)
    && isModuleCapability(value.modules.p3)
    && isPlannedModule(value.modules.p4)
    && typeof value.features.p3_llm_draft === "boolean"
    && typeof value.features.unified_retrieval === "boolean"
    && (value.features.customerops_default_mode === "p1"
      || value.features.customerops_default_mode === "unified");
}

export class CapabilityClientError extends Error {
  constructor(
    message: string,
    public readonly status?: number,
  ) {
    super(message);
    this.name = "CapabilityClientError";
  }
}

export async function getCapabilities(signal?: AbortSignal): Promise<CapabilitiesResponse> {
  const response = await publicApiFetch(apiPath("/api/capabilities"), {
    method: "GET",
    headers: { Accept: "application/json" },
    signal,
  });

  if (!response.ok) {
    throw new CapabilityClientError("Capability request failed.", response.status);
  }

  let body: unknown;
  try {
    body = await response.json() as unknown;
  } catch {
    throw new CapabilityClientError("Capability response is not valid JSON.", response.status);
  }

  if (!isCapabilitiesResponse(body)) {
    throw new CapabilityClientError("Capability response does not match the public contract.", response.status);
  }
  return body;
}
