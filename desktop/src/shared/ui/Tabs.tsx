import type { KeyboardEvent } from "react";

/** Ids que ligam a aba ao painel (aria-controls / aria-labelledby). */
export const tabId = (prefix: string, id: string) => `${prefix}-tab-${id}`;
export const panelId = (prefix: string, id: string) => `${prefix}-panel-${id}`;

/** Props do painel da aba ativa. */
export function tabPanelProps(prefix: string, id: string) {
  return { role: "tabpanel", id: panelId(prefix, id), "aria-labelledby": tabId(prefix, id) } as const;
}

/** Setas, Home e End movem o foco entre as abas e já ativam a aba (ativação automática). */
export function onTabListKeyDown(event: KeyboardEvent<HTMLElement>) {
  const tabs = Array.from(event.currentTarget.querySelectorAll<HTMLElement>('[role="tab"]'));
  const index = tabs.indexOf(document.activeElement as HTMLElement);
  if (index < 0) return;
  const target = { ArrowRight: index + 1, ArrowLeft: index - 1, Home: 0, End: tabs.length - 1 }[event.key];
  if (target === undefined) return;
  event.preventDefault();
  const tab = tabs[(target + tabs.length) % tabs.length];
  tab?.focus();
  tab?.click();
}
