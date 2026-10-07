/// <reference types="vite/client" />

/** Version lue dans package.json au moment du build (voir vite.config.ts > define). */
declare const __APP_VERSION__: string;

interface ImportMetaEnv {
  /** Adresse du pont de dev (engine/dev_bridge.py). Défaut : http://127.0.0.1:8765 */
  readonly VITE_HELPVA_PONT?: string;
}
