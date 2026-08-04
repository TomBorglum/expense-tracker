/// <reference types="vite/client" />

interface ViteTypeOptions {
  // Drops the `any` index signature vite/client puts on ImportMetaEnv. Without it
  // `import.meta.env.VITE_ANYTHING` types as `any`, which both hides a typo and trips
  // typescript-eslint's no-unsafe-* rules the moment the value is used.
  strictImportMetaEnv: unknown;
}

interface ImportMetaEnv {
  // Declared in .env; see the comment there for why it lives in that file.
  readonly VITE_API_BASE_URL: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
