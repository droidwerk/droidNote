import type { ReactElement } from "react";

export type IconName =
  | "console"
  | "chat"
  | "settings"
  | "search"
  | "mic"
  | "system"
  | "voice"
  | "play"
  | "pause"
  | "plus"
  | "more"
  | "close"
  | "export"
  | "trash"
  | "folder"
  | "check"
  | "spark"
  | "refresh"
  | "arrow"
  | "dictation"
  | "lecture"
  | "meeting"
  | "lock"
  | "cloud"
  | "chip"
  | "tasks"
  | "calendar"
  | "shield"
  | "edit"
  | "attach"
  | "expand"
  | "collapse"
  | "rail"
  | "mindmap"
  | "memory";

const PATHS: Record<IconName, ReactElement> = {
  console: (
    <>
      <circle cx="12" cy="12" r="2.6" />
      <path d="M7.4 7.4a6.5 6.5 0 0 0 0 9.2M16.6 7.4a6.5 6.5 0 0 1 0 9.2" />
      <path d="M4.3 4.3a10.9 10.9 0 0 0 0 15.4M19.7 4.3a10.9 10.9 0 0 1 0 15.4" />
    </>
  ),
  chat: (
    <>
      <path d="M4.5 5.5h15v10h-8l-4.5 3.5v-3.5h-2.5z" />
      <path d="M8 9.5h8M8 12.5h5" />
    </>
  ),
  settings: (
    <>
      <path d="M4 7h9M17 7h3M4 12h3M11 12h9M4 17h7M15 17h5" />
      <circle cx="15" cy="7" r="2" />
      <circle cx="9" cy="12" r="2" />
      <circle cx="13" cy="17" r="2" />
    </>
  ),
  search: (
    <>
      <circle cx="10.5" cy="10.5" r="5.5" />
      <path d="m15 15 4.5 4.5" />
    </>
  ),
  mic: (
    <>
      <rect x="9" y="3.5" width="6" height="11" rx="3" />
      <path d="M5.5 11.5a6.5 6.5 0 0 0 13 0M12 18v2.5" />
    </>
  ),
  system: (
    <>
      <rect x="3.5" y="5" width="17" height="11" rx="1.5" />
      <path d="M9 20h6M12 16v4" />
      <path d="M8.5 10.5h1M11.5 9v3M14.5 8v5" />
    </>
  ),
  voice: (
    <>
      <path d="M4 12h1.5M7 9v6M10 6v12M13 8.5v7M16 10.5v3M19 12h1" />
    </>
  ),
  play: <path d="M8 5.5v13l10.5-6.5z" />,
  pause: <path d="M8.5 5.5v13M15.5 5.5v13" />,
  plus: <path d="M12 5v14M5 12h14" />,
  more: (
    <>
      <circle cx="6" cy="12" r="1" />
      <circle cx="12" cy="12" r="1" />
      <circle cx="18" cy="12" r="1" />
    </>
  ),
  close: <path d="m6.5 6.5 11 11M17.5 6.5l-11 11" />,
  export: (
    <>
      <path d="M12 15V4M7.5 8.5 12 4l4.5 4.5" />
      <path d="M5 13.5V19h14v-5.5" />
    </>
  ),
  trash: (
    <>
      <path d="M5 7h14M10 4h4M7 7l.8 12h8.4L17 7" />
    </>
  ),
  folder: (
    <>
      <path d="M3.5 7V18.5h17V8.5h-9L9.5 6h-6z" />
    </>
  ),
  check: <path d="m5.5 12.5 4 4 9-9" />,
  spark: (
    <>
      <path d="M12 3.5v4M12 16.5v4M3.5 12h4M16.5 12h4" />
      <path d="m7 7 1.8 1.8M15.2 15.2 17 17M7 17l1.8-1.8M15.2 8.8 17 7" />
    </>
  ),
  refresh: (
    <>
      <path d="M19 12a7 7 0 1 1-2.05-4.95" />
      <path d="M19 4.5V8h-3.5" />
    </>
  ),
  arrow: <path d="M5 12h14M13.5 6.5 19 12l-5.5 5.5" />,
  dictation: (
    <>
      <rect x="9" y="3.5" width="6" height="10" rx="3" />
      <path d="M6.5 11a5.5 5.5 0 0 0 11 0M12 16.5V20M9 20h6" />
    </>
  ),
  lecture: (
    <>
      <path d="m3 9 9-4.5L21 9l-9 4.5z" />
      <path d="M7 11v4.5c1.4 1.3 3 2 5 2s3.6-.7 5-2V11" />
    </>
  ),
  meeting: (
    <>
      <circle cx="8.5" cy="9" r="2.5" />
      <circle cx="15.5" cy="9" r="2.5" />
      <path d="M4 18.5c.6-2.6 2.3-4 4.5-4s3.9 1.4 4.5 4M11 18.5c.6-2.6 2.3-4 4.5-4s3.9 1.4 4.5 4" />
    </>
  ),
  lock: (
    <>
      <rect x="5.5" y="10.5" width="13" height="9" rx="1.5" />
      <path d="M8.5 10.5V8a3.5 3.5 0 0 1 7 0v2.5" />
    </>
  ),
  cloud: <path d="M7.5 18.5h10a4 4 0 0 0 .6-7.95A5.5 5.5 0 0 0 7.6 9.5a4.5 4.5 0 0 0-.1 9z" />,
  chip: (
    <>
      <rect x="7" y="7" width="10" height="10" rx="1.2" />
      <path d="M10 3.5V7M14 3.5V7M10 17v3.5M14 17v3.5M3.5 10H7M3.5 14H7M17 10h3.5M17 14h3.5" />
    </>
  ),
  tasks: (
    <>
      <path d="m4.5 7 1.6 1.6L9 5.7M4.5 13l1.6 1.6L9 11.7" />
      <path d="M12 7.2h7.5M12 13.2h7.5M5 19h14.5" />
    </>
  ),
  calendar: (
    <>
      <rect x="4" y="5.5" width="16" height="14" rx="2" />
      <path d="M4 10h16M8.5 3.5v4M15.5 3.5v4M8 14h2.5" />
    </>
  ),
  rail: (
    <>
      <rect x="4" y="5" width="16" height="14" rx="2" />
      <path d="M9.5 5v14" />
    </>
  ),
  mindmap: (
    <>
      <circle cx="12" cy="12" r="2.6" />
      <circle cx="5" cy="6.5" r="1.8" />
      <circle cx="19" cy="6.5" r="1.8" />
      <circle cx="5" cy="17.5" r="1.8" />
      <circle cx="19" cy="17.5" r="1.8" />
      <path d="M10 10.5 6.4 7.7M14 10.5l3.6-2.8M10 13.5l-3.6 2.8M14 13.5l3.6 2.8" />
    </>
  ),
  memory: (
    <>
      <path d="M12 4.5a4 4 0 0 0-4 4v1.2a3.2 3.2 0 0 0-1.5 6v.3a3.5 3.5 0 0 0 5.5 2.9 3.5 3.5 0 0 0 5.5-2.9v-.3a3.2 3.2 0 0 0-1.5-6V8.5a4 4 0 0 0-4-4z" />
      <path d="M12 4.5v14.6M8 10.5h4M12 14h4" />
    </>
  ),
  expand: <path d="m6.5 9.5 5.5 5.5 5.5-5.5" />,
  collapse: <path d="m6.5 14.5 5.5-5.5 5.5 5.5" />,
  attach: <path d="M19 11.5 12 18.5a4.6 4.6 0 0 1-6.5-6.5l7.2-7.2a3 3 0 0 1 4.3 4.3l-7.1 7.1a1.5 1.5 0 0 1-2.1-2.1l6.5-6.5" />,
  edit: <path d="M14.5 5.5 18.5 9.5M4.5 19.5l1-4.2L15.8 5a1.4 1.4 0 0 1 2 0l1.2 1.2a1.4 1.4 0 0 1 0 2L8.7 18.5z" />,
  shield: (
    <>
      <path d="M12 3.8 5.5 6.3v5.2c0 4.1 2.7 7.2 6.5 8.7 3.8-1.5 6.5-4.6 6.5-8.7V6.3z" />
      <path d="m9.2 12.1 2 2 3.8-3.9" />
    </>
  ),
};

interface IconProps {
  name: IconName;
  size?: number;
  className?: string;
  title?: string;
}

export function Icon({ name, size = 18, className, title }: IconProps) {
  return (
    <svg
      className={className ? `icon ${className}` : "icon"}
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.6}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden={title ? undefined : true}
      role={title ? "img" : undefined}
    >
      {title ? <title>{title}</title> : null}
      {PATHS[name]}
    </svg>
  );
}
