"use client";

import { useState, useEffect } from "react";

interface JsonHighlightProps {
  data: unknown;
  theme?: "dark" | "light";
  maxHeight?: string;
}

/**
 * Syntax-highlighted JSON display component (issue #543).
 * Supports dark/light themes and copy-to-clipboard functionality.
 */
export function JsonHighlight({ 
  data, 
  theme = "dark",
  maxHeight = "300px" 
}: JsonHighlightProps) {
  const [copied, setCopied] = useState(false);
  const jsonString = JSON.stringify(data, null, 2);

  const copyToClipboard = async () => {
    try {
      await navigator.clipboard.writeText(jsonString);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch (err) {
      console.error("Failed to copy:", err);
    }
  };

  const getColorStyles = () => {
    if (theme === "dark") {
      return {
        key: "#00ff9c",
        string: "#00d4ff",
        number: "#ffaa00",
        boolean: "#ff66ff",
        null: "#888",
      };
    }
    return {
      key: "#0066cc",
      string: "#cc0000",
      number: "#ff6600",
      boolean: "#9900cc",
      null: "#666",
    };
  };

  const highlightJson = (json: string): string => {
    const colors = getColorStyles();
    // Simple regex-based syntax highlighting
    return json
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(
        /("(\\u[a-zA-Z0-9]{4}|\\[^u]|[^\\"])*"(\s*:)?|\b(true|false|null)\b|-?\d+(?:\.\d*)?(?:[eE][+\-]?\d+)?)/g,
        (match) => {
          let color = colors.number;
          let fontWeight = "normal";
          let fontStyle = "normal";
          
          if (/^"/.test(match)) {
            if (/:$/.test(match)) {
              color = colors.key;
              fontWeight = "500";
            } else {
              color = colors.string;
            }
          } else if (/true|false/.test(match)) {
            color = colors.boolean;
            fontWeight = "600";
          } else if (/null/.test(match)) {
            color = colors.null;
            fontStyle = "italic";
          }
          return `<span style="color: ${color}; font-weight: ${fontWeight}; font-style: ${fontStyle};">${match}</span>`;
        }
      );
  };

  const themeStyles = theme === "dark" ? {
    background: "rgba(0, 0, 0, 0.3)",
    border: "1px solid rgba(0, 212, 255, 0.3)",
    color: "#d6f7ff",
  } : {
    background: "rgba(255, 255, 255, 0.95)",
    border: "1px solid rgba(0, 0, 0, 0.2)",
    color: "#1a1a1a",
  };

  return (
    <div style={{ position: "relative" }}>
      <button
        type="button"
        onClick={copyToClipboard}
        style={{
          position: "absolute",
          top: "0.5rem",
          right: "0.5rem",
          padding: "0.4rem 0.8rem",
          fontSize: "0.75rem",
          background: theme === "dark" ? "rgba(0, 212, 255, 0.2)" : "rgba(0, 0, 0, 0.1)",
          border: `1px solid ${theme === "dark" ? "rgba(0, 212, 255, 0.5)" : "rgba(0, 0, 0, 0.3)"}`,
          borderRadius: "4px",
          color: theme === "dark" ? "#00d4ff" : "#000",
          cursor: "pointer",
          transition: "all 0.2s ease",
          zIndex: 1,
        }}
        onMouseEnter={(e) => {
          e.currentTarget.style.background = theme === "dark" ? "rgba(0, 212, 255, 0.3)" : "rgba(0, 0, 0, 0.2)";
        }}
        onMouseLeave={(e) => {
          e.currentTarget.style.background = theme === "dark" ? "rgba(0, 212, 255, 0.2)" : "rgba(0, 0, 0, 0.1)";
        }}
      >
        {copied ? "✓ Copied!" : "📋 Copy"}
      </button>
      
      <pre
        style={{
          ...themeStyles,
          padding: "0.75rem",
          paddingTop: "2.5rem",
          borderRadius: "4px",
          overflow: "auto",
          maxHeight,
          fontSize: "0.8rem",
          fontFamily: "monospace",
          lineHeight: "1.5",
        }}
        dangerouslySetInnerHTML={{ __html: highlightJson(jsonString) }}
      />
    </div>
  );
}
