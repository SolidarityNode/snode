import "leaflet/dist/leaflet.css";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router";

import { App } from "./App";
import { SessionProvider } from "./app/SessionProvider";
import { I18nProvider } from "./i18n/I18nProvider";
import "./styles.css";

const root = document.getElementById("root");
if (!root) {
  throw new Error("#root element missing");
}

createRoot(root).render(
  <StrictMode>
    <I18nProvider>
      <SessionProvider>
        <BrowserRouter>
          <App />
        </BrowserRouter>
      </SessionProvider>
    </I18nProvider>
  </StrictMode>,
);
