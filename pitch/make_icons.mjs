// Renders Lucide icons (ISC license) to transparent PNGs for the deck, via React SSR + Playwright Chromium.
import { chromium } from "@playwright/test";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import * as L from "lucide-react";
import { mkdirSync } from "node:fs";

const OUT = "pitch/assets/icons";
mkdirSync(OUT, { recursive: true });
const COLORS = { teal: "#2DD4BF", white: "#F2F6FC", rose: "#FB7185", amber: "#FBBF24", sky: "#7DD3FC", muted: "#9AA9C2" };
const ICONS = {
  shield: "ShieldCheck", bot: "Bot", database: "Database", key: "KeyRound", ban: "Ban", check: "CircleCheck",
  user: "UserRound", network: "Network", sparkles: "Sparkles", lock: "Lock", building: "Building2", bank: "Landmark",
  headset: "Headset", chart: "ChartColumn", route: "Route", x: "CircleX", search: "FileSearch", scroll: "ScrollText",
  brain: "BrainCircuit", filter: "Filter", users: "Users", zap: "Zap", mail: "Mail", skull: "Skull",
};
const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 256, height: 256 } });
let n = 0;
for (const [name, comp] of Object.entries(ICONS)) {
  const C = L[comp];
  if (!C) throw new Error(`missing lucide icon ${comp}`);
  for (const [cname, hex] of Object.entries(COLORS)) {
    const svg = renderToStaticMarkup(createElement(C, { size: 256, color: hex, strokeWidth: 1.75 }));
    await page.setContent(`<html><body style="margin:0;background:transparent">${svg}</body></html>`);
    await page.locator("svg").screenshot({ path: `${OUT}/${name}-${cname}.png`, omitBackground: true });
    n++;
  }
}
await browser.close();
console.log(`rendered ${n} icon PNGs -> ${OUT}`);
