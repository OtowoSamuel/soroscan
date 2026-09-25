self.onmessage = (e: MessageEvent) => {
  const { events, format } = e.data;

  try {
    let output: string;
    if (format === "json") {
      output = JSON.stringify(events, null, 2);
    } else {
      output = convertToCSV(events);
    }

    const blob = new Blob([output], {
      type: format === "json" ? "application/json" : "text/csv",
    });

    self.postMessage({ success: true, blob, format });
  } catch (error) {
    self.postMessage({ success: false, error: String(error) });
  }
};

function convertToCSV(events: unknown[]): string {
  if (events.length === 0) return "";

  const keys = Object.keys(events[0] as Record<string, unknown>);
  const header = keys.join(",");
  const rows = events.map((event) => {
    const obj = event as Record<string, unknown>;
    return keys
      .map((key) => {
        const val = obj[key];
        const str = val === null || val === undefined ? "" : String(val);
        if (str.includes(",") || str.includes('"') || str.includes("\n")) {
          return `"${str.replace(/"/g, '""')}"`;
        }
        return str;
      })
      .join(",");
  });

  return [header, ...rows].join("\n");
}
