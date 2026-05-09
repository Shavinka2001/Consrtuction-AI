import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Prevent webpack from bundling Prisma's native runtime binaries and
  // MongoDB-specific .mjs query engine files. Prisma must be loaded by
  // Node.js directly, not inlined into the Next.js server bundle.
  serverExternalPackages: ['@prisma/client', '@prisma/engines', 'bcryptjs'],
  images: {
    remotePatterns: [
      {
        protocol: 'https',
        hostname: 'upload.wikimedia.org',
      },
    ],
  },
};

export default nextConfig;
