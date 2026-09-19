import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { App } from "./App";
import { resolveEndpoints } from "./config";
import "./index.css";

const root = document.getElementById("root");
if (!root) throw new Error("no #root element");

void resolveEndpoints(window.location.origin, import.meta.env.DEV).then((endpoints) => {
  createRoot(root).render(
    <StrictMode>
      <App endpoints={endpoints} />
    </StrictMode>,
  );
});
