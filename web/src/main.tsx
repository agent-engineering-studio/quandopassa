import "@mantine/core/styles.css";
import "@mantine/notifications/styles.css";
import "leaflet/dist/leaflet.css";
import "./styles.css";

import { MantineProvider, createTheme } from "@mantine/core";
import { Notifications } from "@mantine/notifications";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";

const tema = createTheme({
  primaryColor: "blue",
  fontFamily: "'Titillium Web', system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif",
  defaultRadius: "md",
});

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <MantineProvider theme={tema} defaultColorScheme="auto">
      <Notifications position="top-center" />
      <App />
    </MantineProvider>
  </StrictMode>,
);
