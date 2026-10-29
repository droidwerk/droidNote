import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { App } from "./app/App";
import { MiniConsole } from "./features/mini/MiniConsole";
import { isMiniRoute } from "./shared/lib/miniWindow";
import { ConfirmProvider } from "./shared/ui/ConfirmDialog";
import { I18nProvider } from "./shared/i18n";
import { ThemeProvider } from "./shared/lib/theme";
import { ToastProvider } from "./shared/ui/Toast";
import "./shared/styles/tokens.css";
import "./shared/styles/shell.css";
import "./shared/styles/console.css";
import "./shared/styles/pages.css";
import "./shared/styles/workflow.css";
import "./shared/styles/planning.css";
import "./shared/styles/library.css";
import "./shared/styles/assist.css";
import "./shared/styles/focus.css";
import "./shared/styles/ai.css";
import "./shared/styles/graph.css";
import "./shared/styles/doc.css";
import "./shared/styles/tips.css";

const root = document.getElementById("root");
if (!root) {
  throw new Error("root element missing");
}

createRoot(root).render(
  <StrictMode>
    <ThemeProvider>
      <I18nProvider>
        <ToastProvider>
          <ConfirmProvider>{isMiniRoute() ? <MiniConsole /> : <App />}</ConfirmProvider>
        </ToastProvider>
      </I18nProvider>
    </ThemeProvider>
  </StrictMode>,
);
