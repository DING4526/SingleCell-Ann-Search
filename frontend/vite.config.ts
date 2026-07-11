import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";
import Components from "unplugin-vue-components/vite";
import { AntDesignVueResolver } from "unplugin-vue-components/resolvers";

export default defineConfig({
  plugins: [
    vue(),
    Components({
      dts: false,
      resolvers: [AntDesignVueResolver({ importStyle: false })],
    }),
  ],
  resolve: {
    alias: {
      "@": "/src",
      buffer: "buffer/",
    },
  },
  define: {
    global: "globalThis",
  },
  server: {
    port: 5173,
    proxy: {
      "/api": "http://127.0.0.1:5000",
      "/assets": "http://127.0.0.1:5000",
    },
  },
  build: {
    // The only chunk above the default threshold is the lazy custom Plotly
    // runtime (Core + ScatterGL only). All eagerly reachable chunks remain
    // below 500 kB; keep the audited lazy module as one stable registry.
    chunkSizeWarningLimit: 1_300,
  },
});
