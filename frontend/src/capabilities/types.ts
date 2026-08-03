export type CapabilityEnvironment = "local" | "test" | "staging" | "production";

export type CapabilityAuthority = "local_docker" | "deployed_environment";

export type CapabilityApiStatus =
  | "available"
  | "local_only"
  | "degraded"
  | "unavailable"
  | "planned";

export type CapabilityDisplayStatus = CapabilityApiStatus | "unknown";

export type CapabilityModuleKey = "p1" | "p2" | "p3" | "p4";

export type InfrastructureAvailability = "available" | "unavailable";
export type StorageAvailability = InfrastructureAvailability | "local_only";

export interface ModuleCapability<TStatus extends CapabilityApiStatus = CapabilityApiStatus> {
  status: TStatus;
  reason_codes: string[];
}

export interface CapabilitiesResponse {
  environment: CapabilityEnvironment;
  authority: CapabilityAuthority;
  auth: {
    mode: "disabled" | "token";
    safe_for_environment: boolean;
  };
  infrastructure: {
    database: InfrastructureAvailability;
    pgvector: InfrastructureAvailability;
    asset_storage: StorageAvailability;
    export_storage: StorageAvailability;
  };
  modules: {
    p1: ModuleCapability<Exclude<CapabilityApiStatus, "planned">>;
    p2: ModuleCapability<Exclude<CapabilityApiStatus, "planned">>;
    p3: ModuleCapability<Exclude<CapabilityApiStatus, "planned">>;
    p4: ModuleCapability<"planned">;
  };
  features: {
    p3_llm_draft: boolean;
    unified_retrieval: boolean;
    customerops_default_mode: "p1" | "unified";
  };
}

export interface CapabilityDisplayState {
  status: CapabilityDisplayStatus;
  reasonCodes: string[];
}

export type CapabilityModuleDisplayState = Record<CapabilityModuleKey, CapabilityDisplayState>;
