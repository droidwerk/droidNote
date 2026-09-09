import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { App } from "./app/App";
import { ConfirmProvider } from "./shared/ui/ConfirmDialog";
import { ThemeProvider } from "./shared/lib/theme";
import { ToastProvider } from "./shared/ui/Toast";
import "./shared/styles/tokens.css";

const root = document.getElementById("root");
if (!root) {
  throw new Error("root element missing");
}

createRoot(root).render(
  <StrictMode>
    <ThemeProvider>
      <ToastProvider>
        <ConfirmProvider>
          <App />
        </ConfirmProvider>
      </ToastProvider>
    </ThemeProvider>
  </StrictMode>,
);
