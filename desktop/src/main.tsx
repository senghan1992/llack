import React from "react";
import ReactDOM from "react-dom/client";

import "@fontsource/schibsted-grotesk/700.css";
import "@fontsource/instrument-sans/400.css";
import "@fontsource/instrument-sans/500.css";
import "@fontsource/instrument-sans/600.css";
import "@fontsource/dm-mono/400.css";
import "@fontsource/dm-mono/500.css";

import "./styles/app.css";
import App from "./App";

document.documentElement.classList.add("js");

const container = document.getElementById("root");
if (!container) throw new Error("#root is missing from index.html");

ReactDOM.createRoot(container).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
