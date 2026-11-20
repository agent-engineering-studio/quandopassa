import "bootstrap-italia/dist/css/bootstrap-italia.min.css";
import "leaflet/dist/leaflet.css";
import "../styles.css";
import "./admin.css";

import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import AdminApp from "./AdminApp";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <AdminApp />
  </StrictMode>,
);
