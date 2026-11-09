import "bootstrap-italia/dist/css/bootstrap-italia.min.css";
import "leaflet/dist/leaflet.css";
import "./styles.css";

import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import Verifica from "./components/Verifica";
import { Notifiche } from "./notifiche";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <Notifiche />
    {window.location.pathname.startsWith("/verifica") ? <Verifica /> : <App />}
  </StrictMode>,
);
