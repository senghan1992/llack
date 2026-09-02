import React from "react";
import ReactDOM from "react-dom/client";

import { App } from "@/app/App";
import { ErrorBoundary } from "@/components/ErrorBoundary";
import "@/styles/global.css";

const root = document.getElementById("root");
if (!root) throw new Error("#root is missing from index.html");

ReactDOM.createRoot(root).render(
  <React.StrictMode>
    <ErrorBoundary>
      <App />
    </ErrorBoundary>
  </React.StrictMode>,
);
