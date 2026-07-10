import type { NextConfig } from "next";

const frameAncestors =
  process.env.FRAME_ANCESTORS ??
  "'self' https://aletheia.com.ng https://www.aletheia.com.ng https://hera-snowy.vercel.app";

const nextConfig: NextConfig = {
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [{ key: "Content-Security-Policy", value: `frame-ancestors ${frameAncestors};` }],
      },
    ];
  },
};

export default nextConfig;
