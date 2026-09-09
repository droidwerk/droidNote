export interface SaveFilter {
  name: string;
  extensions: string[];
}

export type SaveResult =
  | { status: "saved"; path: string | null }
  | { status: "cancelled" }
  | { status: "error"; message: string };

function isTauri(): boolean {
  return "__TAURI_INTERNALS__" in window;
}

function downloadInBrowser(blob: Blob, suggestedName: string): void {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = suggestedName;
  anchor.click();
  URL.revokeObjectURL(url);
}

export async function saveBlob(
  blob: Blob,
  suggestedName: string,
  filters: SaveFilter[],
): Promise<SaveResult> {
  if (!isTauri()) {
    downloadInBrowser(blob, suggestedName);
    return { status: "saved", path: null };
  }

  try {
    const dialog = await import("@tauri-apps/plugin-dialog");
    const path = await dialog.save({
      defaultPath: suggestedName,
      filters: filters.length ? filters : undefined,
    });
    if (!path) return { status: "cancelled" };

    const buffer = new Uint8Array(await blob.arrayBuffer());
    const { invoke } = await import("@tauri-apps/api/core");
    await invoke("write_export_file", { path, bytes: Array.from(buffer) });
    return { status: "saved", path };
  } catch (error) {
    return {
      status: "error",
      message: error instanceof Error ? error.message : "Falha ao gravar o arquivo",
    };
  }
}

export function parentDirectory(path: string): string {
  const index = Math.max(path.lastIndexOf("/"), path.lastIndexOf("\\"));
  return index === -1 ? path : path.slice(0, index);
}

export async function openLocalPath(path: string): Promise<void> {
  if (!path) return;
  try {
    const module = await import("@tauri-apps/plugin-shell");
    await module.open(path);
  } catch {
    /* browser / sem plugin */
  }
}
