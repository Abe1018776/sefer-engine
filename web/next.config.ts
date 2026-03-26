import type { NextConfig } from 'next';

const nextConfig: NextConfig = {
  // Playwright launches a separate Chromium process — exclude it from the
  // serverless bundle so Next.js doesn't try to inline the binary.
  serverExternalPackages: ['playwright'],
};

export default nextConfig;
