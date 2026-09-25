import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import sirv from "sirv";
import { resolve } from "node:path";

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react(), {
    name: 'processed-media',
    configureServer(server) {
      // Vite snapshots public files at startup. ROS processing creates files later.
      const serve = sirv(resolve(server.config.publicDir, 'processed'), { dev: true });
      server.middlewares.use('/processed', (req, res) => {
        serve(req, res, () => {
          res.statusCode = 404;
          res.end('Processed media not found');
        });
      });
    },
  }],
  server: {
    // Docker Desktop bind mounts may not emit Linux file-change events.
    watch: { usePolling: true, interval: 500, ignored: ['**/public/processed/**'] },
    host: "0.0.0.0",
    port: 5173,
    historyApiFallback: true,
    publicDir: 'public',
    // proxy: {
    //   "/api": {
    //     target: "http://0.0.0.0:8000",
    //     changeOrigin: true,
    //     secure: false,
    //   },
    // },
  },
});
