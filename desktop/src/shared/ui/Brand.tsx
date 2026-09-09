import { useState } from "react";

import droidnoteOnDark from "../../assets/logo-droidnote.png";
import droidnoteOnLight from "../../assets/logo-droidnote-on-light.png";
import droidwerkOnDark from "../../assets/logo-droidwerk.png";
import droidwerkOnLight from "../../assets/logo-droidwerk-on-light.png";
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
      <div className="brand-fallback" role="img" aria-label="DroidNote">
        <span className="brand-mark">D</span>
        <strong>DroidNote</strong>
      </div>
    );
  }

  return (
    <span className={`brand-lockup brand-logo-${size}`}>
      <img
        className="brand-logo brand-logo-on-dark"
        src={droidnoteOnDark}
        alt="droidNote"
        onError={() => setFailed(true)}
      />
      <img
        className="brand-logo brand-logo-on-light"
        src={droidnoteOnLight}
        alt=""
        aria-hidden
        onError={() => setFailed(true)}
      />
    </span>
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
        <>
          <img
            className="brand-logo-on-dark"
            src={droidwerkOnDark}
            alt="DroidWerk"
            onError={() => setFailed(true)}
          />
          <img
            className="brand-logo-on-light"
            src={droidwerkOnLight}
            alt=""
            aria-hidden
            onError={() => setFailed(true)}
          />
        </>
      )}
    </button>
  );
}
