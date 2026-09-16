// @ts-check
import react from "@astrojs/react";
import tailwindcss from "@tailwindcss/vite";
import { defineConfig } from "astro/config";

// F7.1. El sitio es estático (SSG, decisión D3): cada página sale como HTML real, y solo lo
// interactivo (cotizador, reserva, My Trip, Customer Help) viaja como isla de React.
export default defineConfig({
  site: "https://www.cabotransportationconcierge.com",
  integrations: [react()],
  vite: { plugins: [tailwindcss()] },
});
