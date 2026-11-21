"use client";

/**
 * SDKDocumentation — Markdown documentation pages with sidebar navigation.
 * Renders the docs/ content inline (no filesystem reads at runtime).
 * All docs are pre-loaded as static strings to avoid Next.js server/client boundary issues.
 */

import * as React from "react";
import Link from "next/link";
import {
  BookOpen,
  Key,
  Webhook,
  FileCode2,
  ChevronRight,
  Search,
  Hash,
  ExternalLink,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { CodeBlock, type CodeBlockLanguage } from "@/components/ui/CodeBlock";

// ---------- Navigation structure ----------

export interface DocNavItem {
  title: string;
  slug: string;
  icon?: React.ComponentType<{ size?: number; className?: string }>;
}

export interface DocNavSection {
  title: string;
  items: DocNavItem[];
}

export const DOC_NAV: DocNavSection[] = [
  {
    title: "Getting Started",
    items: [
      { title: "Quickstart", slug: "quickstart", icon: BookOpen },
      { title: "Authentication", slug: "authentication", icon: Key },
      { title: "Webhooks", slug: "webhooks", icon: Webhook },
    ],
  },
  {
    title: "SDKs",
    items: [
      { title: "Python", slug: "sdks/python", icon: FileCode2 },
      { title: "JavaScript / TypeScript", slug: "sdks/javascript", icon: FileCode2 },
      { title: "Go", slug: "sdks/go", icon: FileCode2 },
    ],
  },
  {
    title: "API Reference",
    items: [
      { title: "Contracts", slug: "api-reference/contracts", icon: FileCode2 },
      { title: "Events", slug: "api-reference/events", icon: FileCode2 },
      { title: "Webhooks Reference", slug: "api-reference/webhooks", icon: Webhook },
    ],
  },
];

// ---------- Simple markdown renderer ----------
// Handles: headers, code blocks, tables, lists, bold, inline code, links, blockquotes

interface MarkdownSection {
  type: "h1" | "h2" | "h3" | "h4" | "paragraph" | "code" | "table" | "ul" | "ol" | "blockquote" | "hr";
  content?: string;
  language?: string;
  rows?: string[][];
  headers?: string[];
  items?: string[];
}

function parseMarkdown(markdown: string): MarkdownSection[] {
  const lines = markdown.split("\n");
  const sections: MarkdownSection[] = [];
  let i = 0;

  while (i < lines.length) {
    const line = lines[i];

    // Fenced code block
    if (line.startsWith("```")) {
      const lang = line.slice(3).trim() || "text";
      const codeLines: string[] = [];
      i++;
      while (i < lines.length && !lines[i].startsWith("```")) {
        codeLines.push(lines[i]);
        i++;
      }
      sections.push({ type: "code", content: codeLines.join("\n"), language: lang });
      i++;
      continue;
    }

    // Heading
    const h1Match = line.match(/^# (.+)$/);
    if (h1Match) { sections.push({ type: "h1", content: h1Match[1] }); i++; continue; }
    const h2Match = line.match(/^## (.+)$/);
    if (h2Match) { sections.push({ type: "h2", content: h2Match[1] }); i++; continue; }
    const h3Match = line.match(/^### (.+)$/);
    if (h3Match) { sections.push({ type: "h3", content: h3Match[1] }); i++; continue; }
    const h4Match = line.match(/^#### (.+)$/);
    if (h4Match) { sections.push({ type: "h4", content: h4Match[1] }); i++; continue; }

    // HR
    if (/^---+$/.test(line.trim())) { sections.push({ type: "hr" }); i++; continue; }

    // Blockquote
    if (line.startsWith("> ")) {
      const quoteLines: string[] = [line.slice(2)];
      i++;
      while (i < lines.length && lines[i].startsWith("> ")) {
        quoteLines.push(lines[i].slice(2));
        i++;
      }
      sections.push({ type: "blockquote", content: quoteLines.join("\n") });
      continue;
    }

    // Table
    if (line.startsWith("|")) {
      const tableLines: string[] = [line];
      i++;
      while (i < lines.length && lines[i].startsWith("|")) {
        tableLines.push(lines[i]);
        i++;
      }
      const parseRow = (row: string) =>
        row.split("|").slice(1, -1).map((cell) => cell.trim());
      const headers = parseRow(tableLines[0]);
      const rows = tableLines.slice(2).map(parseRow);
      sections.push({ type: "table", headers, rows });
      continue;
    }

    // Unordered list
    if (/^[-*] /.test(line)) {
      const items: string[] = [line.slice(2).trim()];
      i++;
      while (i < lines.length && /^[-*] /.test(lines[i])) {
        items.push(lines[i].slice(2).trim());
        i++;
      }
      sections.push({ type: "ul", items });
      continue;
    }

    // Ordered list
    if (/^\d+\. /.test(line)) {
      const items: string[] = [line.replace(/^\d+\. /, "").trim()];
      i++;
      while (i < lines.length && /^\d+\. /.test(lines[i])) {
        items.push(lines[i].replace(/^\d+\. /, "").trim());
        i++;
      }
      sections.push({ type: "ol", items });
      continue;
    }

    // Paragraph (non-empty line)
    if (line.trim()) {
      const paraLines: string[] = [line];
      i++;
      while (i < lines.length && lines[i].trim() && !lines[i].startsWith("#") && !lines[i].startsWith("|") && !lines[i].startsWith(">") && !lines[i].startsWith("```") && !/^[-*] /.test(lines[i]) && !/^\d+\. /.test(lines[i])) {
        paraLines.push(lines[i]);
        i++;
      }
      sections.push({ type: "paragraph", content: paraLines.join(" ") });
      continue;
    }

    i++;
  }

  return sections;
}

// Inline formatting: **bold**, `code`, [link](url)
function renderInline(text: string): React.ReactNode {
  const parts: React.ReactNode[] = [];
  const pattern = /(\*\*[^*]+\*\*|`[^`]+`|\[[^\]]+\]\([^)]+\))/g;
  let lastIndex = 0;
  let match: RegExpExecArray | null;

  while ((match = pattern.exec(text)) !== null) {
    if (match.index > lastIndex) {
      parts.push(text.slice(lastIndex, match.index));
    }
    const token = match[0];
    if (token.startsWith("**")) {
      parts.push(<strong key={match.index} className="text-terminal-white">{token.slice(2, -2)}</strong>);
    } else if (token.startsWith("`")) {
      parts.push(<code key={match.index} className="text-terminal-cyan bg-terminal-dark px-1 font-mono text-[0.875em]">{token.slice(1, -1)}</code>);
    } else {
      const linkMatch = token.match(/\[([^\]]+)\]\(([^)]+)\)/);
      if (linkMatch) {
        const [, label, href] = linkMatch;
        const isExternal = href.startsWith("http");
        parts.push(
          <a
            key={match.index}
            href={href}
            className="text-terminal-cyan hover:underline inline-flex items-center gap-0.5"
            {...(isExternal ? { target: "_blank", rel: "noopener noreferrer" } : {})}
          >
            {label}
            {isExternal && <ExternalLink size={11} aria-hidden="true" />}
          </a>,
        );
      }
    }
    lastIndex = match.index + token.length;
  }

  if (lastIndex < text.length) {
    parts.push(text.slice(lastIndex));
  }

  return parts.length === 1 ? parts[0] : <>{parts}</>;
}

const CODE_LANG_MAP: Record<string, CodeBlockLanguage> = {
  python: "python",
  typescript: "typescript",
  javascript: "javascript",
  ts: "typescript",
  js: "javascript",
  bash: "bash",
  sh: "bash",
  json: "json",
  graphql: "graphql",
  rust: "rust",
  yaml: "yaml",
  go: "text",
};

function renderSection(section: MarkdownSection, idx: number): React.ReactNode {
  switch (section.type) {
    case "h1":
      return <h1 key={idx} className="text-3xl font-bold text-terminal-green mt-2 mb-4 pb-2 border-b border-terminal-green/20">{section.content}</h1>;
    case "h2":
      return <h2 key={idx} className="text-xl font-bold text-terminal-green mt-8 mb-3 flex items-center gap-2"><Hash size={16} className="text-terminal-green/60" aria-hidden="true" />{section.content}</h2>;
    case "h3":
      return <h3 key={idx} className="text-base font-bold text-terminal-cyan mt-6 mb-2">{section.content}</h3>;
    case "h4":
      return <h4 key={idx} className="text-sm font-bold text-terminal-gray mt-4 mb-1 uppercase tracking-widest">{section.content}</h4>;
    case "paragraph":
      return <p key={idx} className="text-sm text-terminal-gray leading-relaxed my-2">{renderInline(section.content ?? "")}</p>;
    case "code":
      return (
        <div key={idx} className="my-4">
          <CodeBlock
            code={section.content ?? ""}
            language={CODE_LANG_MAP[section.language ?? ""] ?? "text"}
            showHeader
            showLineNumbers
          />
        </div>
      );
    case "table":
      return (
        <div key={idx} className="my-4 overflow-x-auto">
          <table className="w-full text-xs border-collapse border border-terminal-green/20">
            <thead>
              <tr className="border-b border-terminal-green/20 bg-terminal-black/50">
                {(section.headers ?? []).map((h, hi) => (
                  <th key={hi} className="text-left px-3 py-2 text-terminal-gray font-normal">{renderInline(h)}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {(section.rows ?? []).map((row, ri) => (
                <tr key={ri} className="border-b border-terminal-green/10">
                  {row.map((cell, ci) => (
                    <td key={ci} className="px-3 py-2 text-terminal-gray">{renderInline(cell)}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      );
    case "ul":
      return (
        <ul key={idx} className="my-2 space-y-1.5 pl-4">
          {(section.items ?? []).map((item, ii) => (
            <li key={ii} className="text-sm text-terminal-gray flex items-start gap-2">
              <span className="text-terminal-green mt-1 shrink-0">▸</span>
              {renderInline(item)}
            </li>
          ))}
        </ul>
      );
    case "ol":
      return (
        <ol key={idx} className="my-2 space-y-1.5 pl-4">
          {(section.items ?? []).map((item, ii) => (
            <li key={ii} className="text-sm text-terminal-gray flex items-start gap-2">
              <span className="text-terminal-cyan shrink-0 min-w-[1.5rem]">{ii + 1}.</span>
              {renderInline(item)}
            </li>
          ))}
        </ol>
      );
    case "blockquote":
      return (
        <div key={idx} className="my-3 border-l-2 border-terminal-warning pl-4 py-1">
          <p className="text-sm text-terminal-warning italic">{section.content}</p>
        </div>
      );
    case "hr":
      return <div key={idx} className="my-6 border-t border-terminal-green/20" />;
    default:
      return null;
  }
}

// ---------- Sidebar ----------

function DocSidebar({
  activeSlug,
  searchQuery,
  onSearchChange,
}: {
  activeSlug: string;
  searchQuery: string;
  onSearchChange: (q: string) => void;
}) {
  return (
    <aside className="w-60 shrink-0 border-r border-terminal-green/20 bg-terminal-black/80 h-full overflow-y-auto" aria-label="Documentation navigation">
      <div className="p-4">
        <div className="relative mb-4">
          <Search size={12} className="absolute left-3 top-1/2 -translate-y-1/2 text-terminal-gray" aria-hidden="true" />
          <input
            type="search"
            value={searchQuery}
            onChange={(e) => onSearchChange(e.target.value)}
            placeholder="Search docs..."
            aria-label="Search documentation"
            className="w-full pl-8 pr-2 py-1.5 text-xs border border-terminal-green/30 bg-terminal-black text-terminal-green placeholder:text-terminal-gray focus:outline-none focus:border-terminal-green"
          />
        </div>

        {DOC_NAV.map((section) => (
          <div key={section.title} className="mb-4">
            <div className="text-[9px] uppercase tracking-widest text-terminal-gray-muted mb-2 px-1">
              {section.title}
            </div>
            <nav>
              {section.items.map((item) => {
                const Icon = item.icon;
                const isActive = activeSlug === item.slug;
                return (
                  <Link
                    key={item.slug}
                    href={`/developer-portal/docs/${item.slug}`}
                    className={cn(
                      "flex items-center gap-2 px-2 py-1.5 text-xs transition-colors rounded-sm",
                      isActive
                        ? "text-terminal-green bg-terminal-green/10"
                        : "text-terminal-gray hover:text-terminal-green hover:bg-terminal-green/5",
                    )}
                    aria-current={isActive ? "page" : undefined}
                  >
                    {Icon && <Icon size={12} aria-hidden="true" />}
                    <span className="flex-1 min-w-0 truncate">{item.title}</span>
                    {isActive && <ChevronRight size={10} aria-hidden="true" />}
                  </Link>
                );
              })}
            </nav>
          </div>
        ))}
      </div>
    </aside>
  );
}

// ---------- Main Component ----------

interface SDKDocumentationProps {
  /** The slug of the document to display (e.g. "sdks/python") */
  slug: string;
  /** Markdown content to render */
  content: string;
  className?: string;
}

export function SDKDocumentation({ slug, content, className }: SDKDocumentationProps) {
  const [searchQuery, setSearchQuery] = React.useState("");
  const sections = React.useMemo(() => parseMarkdown(content), [content]);

  // Filter sections by search query for highlighting
  const filteredSections = searchQuery.trim()
    ? sections.filter(
        (s) =>
          s.content?.toLowerCase().includes(searchQuery.toLowerCase()) ||
          s.items?.some((i) => i.toLowerCase().includes(searchQuery.toLowerCase())),
      )
    : sections;

  return (
    <div className={cn("flex h-full min-h-[600px]", className)} data-testid="sdk-documentation">
      <DocSidebar
        activeSlug={slug}
        searchQuery={searchQuery}
        onSearchChange={setSearchQuery}
      />
      <main className="flex-1 min-w-0 overflow-y-auto p-8">
        {searchQuery.trim() && (
          <div className="mb-4 px-3 py-2 border border-terminal-cyan/20 text-xs text-terminal-cyan">
            Showing {filteredSections.length} section(s) matching &ldquo;{searchQuery}&rdquo;
          </div>
        )}
        <article className="max-w-3xl">
          {(searchQuery.trim() ? filteredSections : sections).map((section, idx) =>
            renderSection(section, idx),
          )}
        </article>
      </main>
    </div>
  );
}
