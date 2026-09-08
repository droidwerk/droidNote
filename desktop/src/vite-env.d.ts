/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_DROIDNOTE_URL?: string;
  readonly VITE_DROIDNOTE_TOKEN?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
