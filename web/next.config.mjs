/** @type {import('next').NextConfig} */
const nextConfig = {
  // Static site: the detector runs in the browser, so no server is needed.
  output: "export",
  images: { unoptimized: true },
};

export default nextConfig;
