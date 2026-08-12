const path = require('path');
const { defineConfig } = require('vitest/config');

module.exports = defineConfig({
  test: {
    environment: 'jsdom',
    globals: true,
    include: ['src/**/*.test.{ts,tsx}'],
    // Default test timeout: 15s (up from vitest's 5s default).
    //
    // We render real React component trees under jsdom in many tests, and
    // GitHub Actions' shared Node.js workers (specifically the
    // "CI - Lint & Test / Frontend Tests & Build" job) consistently
    // measure 6–10s for the heavier MessagesView / GateView / Wormhole
    // contact flows under CI load. On a developer laptop those same tests
    // settle in <1s, so the 5s default was tuned to local dev speed and
    // not to CI runner speed.
    //
    // Concrete history that drove this bump (none of these were real
    // product bugs — all were CI load racing the 5s ceiling on
    // findByText / waitFor against React reconciliation):
    //   PR #226, #237, #261, #262, #265 all flaked on
    //     src/__tests__/mesh/messagesViewFirstContact.test.tsx
    //     src/__tests__/mesh/gateCompatDecryptUx.test.tsx
    //   PR #262's flake was the worst — it fired on the post-merge
    //   Docker Publish run and prevented the AIS SPKI security fix's
    //   image from being published to GHCR until the next PR
    //   cumulatively re-published it.
    //
    // 15s is generous enough to absorb routine CI slowness without
    // masking real "test never settles" bugs (those would still time
    // out, just three rounds later). Individual tests can still pin
    // their own tighter timeout via the third arg to `it()`.
    testTimeout: 15000,
    // Hook timeout follows test timeout — beforeEach/afterEach setup
    // for the heavier component tests has the same CI-load sensitivity.
    hookTimeout: 15000,
  },
  resolve: {
    alias: {
      '@': path.resolve(__dirname, 'src'),
    },
  },
});
