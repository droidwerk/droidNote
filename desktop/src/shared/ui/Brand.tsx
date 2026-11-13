import { useEffect, useState } from "react";

import droidnoteOnDark from "../../assets/logo-droidnote.png";
import droidnoteOnLight from "../../assets/logo-droidnote-on-light.png";
import droidwerkOnDark from "../../assets/logo-droidwerk.png";
import droidwerkOnLight from "../../assets/logo-droidwerk-on-light.png";
import { useI18n } from "../i18n";
import { openExternal } from "../lib/openExternal";
import { siteUrl } from "../lib/whatsNew";

export type BrandSize = "sidebar" | "wizard" | "splash";

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
  const { t, locale } = useI18n();
  const [failed, setFailed] = useState(false);

  return (
    <button
      type="button"
      className={className ? `site-credit ${className}` : "site-credit"}
      onClick={() => void openExternal(siteUrl(locale))}
      aria-label={t("boot.openSite")}
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

export function AppVersion({ className }: { className?: string }) {
  const [version, setVersion] = useState("");

  useEffect(() => {
    void import("@tauri-apps/api/app")
      .then(({ getVersion }) => getVersion())
      .then(setVersion)
      .catch(() => undefined);
  }, []);

  if (!version) return null;
  return (
    <span className={className ? `app-version ${className}` : "app-version"} title={`DroidNote ${version}`}>
      v{version}
    </span>
  );
}
