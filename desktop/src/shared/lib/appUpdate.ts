import { isNewerVersion, normalizeVersion } from "./semver";

const RELEASES_URL = "https://api.github.com/repos/droidwerk/droidNote/releases/latest";
const SKIPPED_KEY = "droidnote.skipped_update";
const SETUP_NAME = "droidnote-setup.exe";

export interface AppUpdateNotice {
  version: string;
  current: string;
  downloadUrl: string;
}

interface GithubAsset {
  name: string;
  browser_download_url: string;
}

interface GithubRelease {
  tag_name: string;
  html_url: string;
  assets: GithubAsset[];
}

function readSkipped(): string | null {
  try {
    return window.localStorage.getItem(SKIPPED_KEY);
  } catch {
    return null;
  }
}

export function rememberSkippedUpdate(version: string): void {
  try {
    window.localStorage.setItem(SKIPPED_KEY, normalizeVersion(version));
  } catch {
    /* private mode */
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function parseRelease(value: unknown): GithubRelease | null {
  if (!isRecord(value)) return null;
  if (typeof value.tag_name !== "string" || typeof value.html_url !== "string") return null;
  if (!Array.isArray(value.assets)) return null;
  const assets: GithubAsset[] = [];
  for (const item of value.assets) {
    if (!isRecord(item)) continue;
    if (typeof item.name !== "string" || typeof item.browser_download_url !== "string") continue;
    assets.push({ name: item.name, browser_download_url: item.browser_download_url });
  }
  return { tag_name: value.tag_name, html_url: value.html_url, assets };
}

function pickDownloadUrl(release: GithubRelease): string {
  const setup = release.assets.find((asset) => asset.name.toLowerCase() === SETUP_NAME);
  if (setup) return setup.browser_download_url;
  const nsis = release.assets.find((asset) => asset.name.toLowerCase().endsWith("-setup.exe"));
  if (nsis) return nsis.browser_download_url;
  return release.html_url;
}

export async function findAppUpdate(currentRaw: string): Promise<AppUpdateNotice | null> {
  if (import.meta.env.DEV) return null;
  const current = normalizeVersion(currentRaw);
  const skipped = readSkipped();
  let response: Response;
  try {
    response = await fetch(RELEASES_URL, {
      headers: { Accept: "application/vnd.github+json" },
    });
  } catch {
    return null;
  }
  if (!response.ok) return null;
  let payload: unknown;
  try {
    payload = await response.json();
  } catch {
    return null;
  }
  const release = parseRelease(payload);
  if (!release) return null;
  const version = normalizeVersion(release.tag_name);
  if (!isNewerVersion(version, current)) return null;
  if (skipped && skipped === version) return null;
  return {
    version,
    current,
    downloadUrl: pickDownloadUrl(release),
  };
}
