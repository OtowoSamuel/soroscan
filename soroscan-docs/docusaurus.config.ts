import {themes as prismThemes} from 'prism-react-renderer';
import type {Config} from '@docusaurus/types';
import type * as Preset from '@docusaurus/preset-classic';

const config: Config = {
  title: 'SoroScan Dev Portal',
  tagline: 'Retro-futuristic terminal-inspired indexing for Soroban',
  favicon: 'img/favicon.ico',

  url: 'https://docs.soroscan.io',
  baseUrl: '/',

  organizationName: 'SoroScan',
  projectName: 'soroscan',

  onBrokenLinks: 'throw',
  onBrokenMarkdownLinks: 'throw',

  i18n: {
    defaultLocale: 'en',
    locales: ['en'],
  },

  presets: [
    [
      'classic',
      {
        docs: {
          path: '../docs',
          routeBasePath: '/',
          sidebarPath: './sidebars.ts',
          editUrl: 'https://github.com/SoroScan/soroscan/tree/main/docs/',
          docItemComponent: '@theme/ApiItem',
        },
        blog: false,
        theme: {
          customCss: './src/css/custom.css',
        },
      } satisfies Preset.Options,
    ],
  ],

  plugins: [
    [
      'docusaurus-plugin-openapi-docs',
      {
        id: 'api', // plugin id
        docsPluginId: 'classic', // configured for preset-classic
        config: {
          soroscan: {
            specPath: 'openapi.json',
            outputDir: '../docs/api-reference',
            sidebarOptions: {
              groupPathsBy: 'tag',
            },
          },
        },
      },
    ],
  ],

  themes: ['docusaurus-theme-openapi-docs'],

  themeConfig: {
    colorMode: {
      defaultMode: 'dark',
      disableSwitch: true,
      respectPrefersColorScheme: false,
    },
    navbar: {
      title: '◆ SOROSCAN',
      logo: {
        alt: 'SoroScan Logo',
        src: 'img/logo.svg',
      },
      items: [
        {
          type: 'docSidebar',
          sidebarId: 'tutorialSidebar',
          position: 'left',
          label: 'Documentation',
        },
        {
          to: '/category/api',
          label: 'API Explorer',
          position: 'left',
        },
        {
          href: 'https://github.com/SoroScan/soroscan',
          label: 'GitHub',
          position: 'right',
        },
      ],
    },
    footer: {
      style: 'dark',
      links: [
        {
          title: 'Docs',
          items: [
            { label: 'Getting Started', to: '/' },
            { label: 'API Overview', to: '/api-overview' },
            { label: 'Python SDK', to: '/sdk-python' },
            { label: 'TypeScript SDK', to: '/sdk-typescript' },
          ],
        },
        {
          title: 'Developer Resources',
          items: [
            { label: 'API Explorer', to: '/api-explorer' },
            { label: 'Cookbook', to: '/cookbook/track-contract-events' },
            { label: 'Changelog', to: '/changelog' },
            { label: 'Rate Limits', to: '/rate-limits' },
          ],
        },
        {
          title: 'Community',
          items: [
            { label: 'Stack Overflow', href: 'https://stackoverflow.com/questions/tagged/soroscan' },
            { label: 'Discord', href: 'https://discord.gg/soroscan' },
            { label: 'GitHub', href: 'https://github.com/SoroScan/soroscan' },
          ],
        },
      ],
      copyright: `Copyright © ${new Date().getFullYear()} SoroScan. EXECUTION_STATUS: SUCCESS [TERMINAL_MODE]`,
    },
    prism: {
      theme: prismThemes.github,
      darkTheme: prismThemes.dracula,
      additionalLanguages: ['python', 'bash', 'json', 'typescript', 'yaml'],
    },
  } satisfies Preset.ThemeConfig,
};

export default config;