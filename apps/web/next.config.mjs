// Fail the build itself, not just first use at runtime, when a non-local build is missing the API
// URL - lib/api.ts throws too, but nothing in this app's prerendered routes happens to import it
// eagerly, so that throw alone wouldn't stop a broken image from being built and pushed to ECR.
if (process.env.NEXT_PUBLIC_APP_ENV !== "local" && !process.env.NEXT_PUBLIC_API_URL) {
  throw new Error(
    "NEXT_PUBLIC_API_URL is not set. Pass it as a Docker build-arg (see infra/README.md) for any " +
      "non-local build (NEXT_PUBLIC_APP_ENV is not \"local\").",
  );
}

/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "standalone",
};

export default nextConfig;
