import type { Config } from 'jest';
import nextJest from 'next/jest.js';

const createJestConfig = nextJest({
  dir: './',
});

const config: Config = {
  coverageProvider: 'v8',
  testEnvironment: 'jsdom',
  setupFilesAfterEnv: ['<rootDir>/jest.setup.ts'],
  // Tell Jest how to resolve the @/ path aliases
  moduleNameMapper: {
    '^@/(.*)$': '<rootDir>/$1',
  },
  // Playwright E2E specs live in tests/ and must not run under Jest
  testPathIgnorePatterns: ['/node_modules/', '/.next/', '/tests/', '/test-results/', '/playwright-report/'],

  // Coverage collection - combined exclusions
  collectCoverageFrom: [
    'src/**/*.{js,jsx,ts,tsx}',
    'app/**/*.{js,jsx,ts,tsx}',
    'components/**/*.{js,jsx,ts,tsx}',
    'lib/**/*.{ts,tsx}',
    'context/**/*.{ts,tsx}',
    'providers/**/*.{ts,tsx}',
    '!**/*.d.ts',
    '!**/node_modules/**',
    '!**/__generated__/**',
    '!**/gql/**',
  ],

  coverageDirectory: 'coverage',
  coverageReporters: ['text', 'text-summary', 'lcov', 'json', 'html'],

  // Keep Jest at its current 40/30/35/40 baseline; Codecov tracks 70% as a longer-term target.
  coverageThreshold: {
    global: {
      lines: 40,
      branches: 30,
      functions: 35,
      statements: 40,
    },
  },
};

export default createJestConfig(config);