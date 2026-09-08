import { useState } from "react";

import droidnote from "../../assets/logo-droidnote.png";
import droidwerk from "../../assets/logo-droidwerk.png";
import { openExternal } from "../lib/openExternal";

export type BrandSize = "sidebar" | "wizard" | "splash";

const DROIDWERK_SITE = "https://www.droidwerk.com.br/";

interface BrandLockupProps {
  size: BrandSize;
}

export function BrandLockup({ size }: BrandLockupProps) {
  const [failed, setFailed] = useState(false);

  if (failed) {
    return (
      <div className="brand-fallback" aria-hidden>
        <span className="brand-mark">D</span>
        <strong>droidNote</strong>
      </div>
    );
  }

  return (
    <img
      className={`brand-logo brand-logo-${size}`}
      src={droidnote}
      alt="droidNote"
      onError={() => setFailed(true)}
    />
  );
}

interface SiteCreditProps {
  className?: string;
}

export function SiteCredit({ className }: SiteCreditProps) {
  const [failed, setFailed] = useState(false);

  return (
    <button
      type="button"
      className={className ? `site-credit ${className}` : "site-credit"}
      onClick={() => void openExternal(DROIDWERK_SITE)}
      aria-label="Abrir o site da DroidWerk"
    >
      {failed ? (
        <span>DroidWerk</span>
      ) : (
        <img src={droidwerk} alt="DroidWerk" onError={() => setFailed(true)} />
      )}
    </button>
  );
}
