import {
  createContext,
  useCallback,
  useContext,
  useId,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import { useT } from "../i18n";
import { Modal } from "./Modal";
import { Button } from "./primitives";

export type ConfirmTone = "danger" | "default";

export interface ConfirmOptions {
  title: string;
  description?: string;
  confirmLabel?: string;
  cancelLabel?: string;
  tone?: ConfirmTone;
  /** Terceiro botão, à esquerda: roda a ação sem fechar o diálogo. */
  extraAction?: { label: string; onClick: () => void };
}

interface ConfirmRequest extends ConfirmOptions {
  id: number;
  resolve: (value: boolean) => void;
}

interface ConfirmContextValue {
  confirm: (options: ConfirmOptions) => Promise<boolean>;
}

const ConfirmContext = createContext<ConfirmContextValue | null>(null);
let nextRequestId = 0;

export function ConfirmProvider({ children }: { children: ReactNode }) {
  const t = useT();
  const [request, setRequest] = useState<ConfirmRequest | null>(null);
  const titleId = useId();
  const descriptionId = useId();

  const confirm = useCallback((options: ConfirmOptions) => {
    return new Promise<boolean>((resolve) => {
      setRequest({ ...options, id: (nextRequestId += 1), resolve });
    });
  }, []);

  const settle = useCallback((value: boolean) => {
    setRequest((current) => {
      current?.resolve(value);
      return null;
    });
  }, []);

  const value = useMemo(() => ({ confirm }), [confirm]);
  const tone = request?.tone ?? "default";

  return (
    <ConfirmContext.Provider value={value}>
      {children}
      {request ? (
        <Modal
          key={request.id}
          onClose={() => settle(false)}
          labelledBy={titleId}
          describedBy={request.description ? descriptionId : undefined}
          className={`confirm-${tone}`}
          initialFocus=".confirm-actions .button-ghost:not(.confirm-extra)"
        >
          <div className="confirm-copy">
            <h2 id={titleId}>{request.title}</h2>
            {request.description ? <p id={descriptionId}>{request.description}</p> : null}
          </div>
          <div className="confirm-actions">
            {request.extraAction ? (
              <Button className="confirm-extra" onClick={request.extraAction.onClick}>
                {request.extraAction.label}
              </Button>
            ) : null}
            <Button onClick={() => settle(false)}>
              {request.cancelLabel ?? t("common.cancel")}
            </Button>
            <Button
              variant={tone === "danger" ? "danger" : "primary"}
              onClick={() => settle(true)}
            >
              {request.confirmLabel ?? t("common.ok")}
            </Button>
          </div>
        </Modal>
      ) : null}
    </ConfirmContext.Provider>
  );
}

export function useConfirm(): (options: ConfirmOptions) => Promise<boolean> {
  const context = useContext(ConfirmContext);
  if (!context) {
    throw new Error("useConfirm precisa de ConfirmProvider");
  }
  return context.confirm;
}
