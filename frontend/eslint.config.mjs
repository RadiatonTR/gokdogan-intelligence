import { defineConfig, globalIgnores } from 'eslint/config';
import nextVitals from 'eslint-config-next/core-web-vitals';
import nextTs from 'eslint-config-next/typescript';

const eslintConfig = defineConfig([
  ...nextVitals,
  ...nextTs,
  {
    files: ['**/*.{ts,tsx}'],
    rules: {
      '@typescript-eslint/no-explicit-any': 'warn',
      '@typescript-eslint/ban-ts-comment': 'warn',
      'react-hooks/set-state-in-effect': 'off',
      'react-hooks/purity': 'off',
      'react-hooks/refs': 'off',
      'prefer-const': 'warn',
      '@typescript-eslint/no-unused-vars': ['warn', { argsIgnorePattern: '^_' }],
    },
  },
  {
    files: ['**/*.test.{ts,tsx}'],
    rules: {
      '@typescript-eslint/no-explicit-any': 'off',
      '@typescript-eslint/no-unused-vars': 'off',
    },
  },
  // These mature modules intentionally keep broad API/controller shapes and
  // dynamic feed payloads. Scope legacy-noise exceptions to the known files so
  // newly added code remains covered by the warning-free release gate.
  {
    files: [
      'src/components/AIIntelPanel.tsx',
      'src/components/GlobalTicker.tsx',
      'src/components/InfonetTerminal/MessagesView.tsx',
      'src/components/IntelligenceCenterPanel.tsx',
      'src/components/MaplibreViewer.tsx',
      'src/components/NewsFeed.tsx',
      'src/components/PredictionsPanel.tsx',
      'src/components/map/dynamicMapLayers.worker.ts',
    ],
    rules: {
      '@typescript-eslint/no-explicit-any': 'off',
    },
  },
  {
    files: [
      'src/app/page.tsx',
      'src/components/GlobalTicker.tsx',
      'src/components/InfonetTerminal/MessagesView.tsx',
      'src/components/InfonetTerminal/PetitionsView.tsx',
      'src/components/MaplibreViewer.tsx',
      'src/components/MeshChat/index.tsx',
      'src/components/MeshChat/useMeshChatController.ts',
      'src/components/OnboardingModal.tsx',
      'src/components/PredictionsPanel.tsx',
      'src/lib/layerPreferences.ts',
      'src/mesh/meshDmClient.ts',
      'src/mesh/meshDmRatchet.ts',
      'src/mesh/wormholeIdentityClient.ts',
    ],
    rules: {
      '@typescript-eslint/no-unused-vars': 'off',
    },
  },
  {
    files: [
      'src/app/LocateBar.tsx',
      'src/components/InfonetTerminal/InfonetShell.tsx',
      'src/components/MaplibreViewer.tsx',
      'src/components/MeshChat/useMeshChatController.ts',
      'src/components/NewsFeed.tsx',
      'src/components/TopRightControls.tsx',
      'src/components/map/hooks/useDynamicMapLayersWorker.ts',
      'src/components/map/hooks/useStaticMapLayersWorker.ts',
    ],
    rules: {
      'react-hooks/exhaustive-deps': 'off',
    },
  },
  {
    files: [
      'src/components/AIIntelPanel.tsx',
      'src/components/InfonetTerminal/ProfileView.tsx',
      'src/components/MaplibreViewer/CctvFullscreenModal.tsx',
      'src/components/NewsFeed.tsx',
    ],
    rules: {
      '@next/next/no-img-element': 'off',
    },
  },
  {
    files: ['scripts/**/*.js'],
    rules: {
      '@typescript-eslint/no-require-imports': 'off',
    },
  },
  {
    files: ['**/*.cjs', 'vitest.config.js'],
    rules: {
      '@typescript-eslint/no-require-imports': 'off',
    },
  },
  // Override default ignores of eslint-config-next.
  globalIgnores([
    // Default ignores of eslint-config-next:
    '.next/**',
    'out/**',
    'build/**',
    'next-env.d.ts',
    'coverage/**',
    'eslint-report.json',
    'src/mesh/privacyCoreWasm/**',
  ]),
]);

export default eslintConfig;
