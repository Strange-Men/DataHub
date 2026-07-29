/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_BASE_URL?: string;
  readonly VITE_P3_LLM_DRAFT_ENABLED?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
