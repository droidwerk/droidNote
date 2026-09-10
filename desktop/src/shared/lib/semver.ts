export function normalizeVersion(raw: string): string {
  return raw.trim().replace(/^v/i, "");
}

function parseParts(raw: string): [number, number, number] | null {
  const core = normalizeVersion(raw).split("-")[0] ?? "";
  const bits = core.split(".");
  if (bits.length < 2 || bits.length > 3) return null;
  const major = Number(bits[0]);
  const minor = Number(bits[1]);
  const patch = bits[2] === undefined ? 0 : Number(bits[2]);
  if (![major, minor, patch].every((n) => Number.isInteger(n) && n >= 0)) return null;
  return [major, minor, patch];
}

export function compareSemver(a: string, b: string): number {
  const left = parseParts(a);
  const right = parseParts(b);
  if (!left || !right) return 0;
  for (let i = 0; i < 3; i += 1) {
    const l = left[i] ?? 0;
    const r = right[i] ?? 0;
    if (l !== r) return l > r ? 1 : -1;
  }
  return 0;
}

export function isNewerVersion(latest: string, current: string): boolean {
  return compareSemver(latest, current) > 0;
}
