import { readdirSync, readFileSync, writeFileSync, unlinkSync } from "fs";
import { join, extname } from "path";
import { fileURLToPath } from "url";

const CJS_DIR = fileURLToPath(new URL("../dist/cjs", import.meta.url));

function walk(dir) {
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const full = join(dir, entry.name);
    if (entry.isDirectory()) {
      walk(full);
    } else if (entry.isFile() && extname(entry.name) === ".js") {
      let src = readFileSync(full, "utf8");
      src = src.replace(/require\("(\.[^"]+)\.js"\)/g, 'require("$1.cjs")');
      const newPath = full.replace(/\.js$/, ".cjs");
      writeFileSync(newPath, src);
      unlinkSync(full);
    }
  }
}

walk(CJS_DIR);
console.log("✓ CJS output renamed to .cjs");