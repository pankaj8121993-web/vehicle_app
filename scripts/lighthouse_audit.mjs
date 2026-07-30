#!/usr/bin/env node
// Guarded Lighthouse driver for FleetFlow Phase 3 (UX-R1 / P3-08).
//
// Runs Lighthouse against the isolated, locally served application for the
// four required pages in both desktop and mobile form factors. Protected
// pages are audited with a real authenticated session: the caller passes a
// `fleet_session` cookie value obtained by logging in through the real API,
// and this driver sends it as a Cookie header on every request so protected
// pages render exactly as an authenticated user sees them.
//
// It never mocks application state and refuses non-local targets.
//
// Usage:
//   node scripts/lighthouse_audit.mjs \
//     --base-url http://127.0.0.1:PORT \
//     --cookie <fleet_session value> \
//     --vehicle-id <id> \
//     --out <output dir>
//
// `lighthouse` and `chrome-launcher` must be resolvable (NODE_PATH may point at
// an install directory). See docs/implementation/LIGHTHOUSE_EVIDENCE.md.

import { launch } from "chrome-launcher";
import lighthouse from "lighthouse";
import fs from "node:fs";
import path from "node:path";

function arg(name, fallback) {
  const i = process.argv.indexOf(`--${name}`);
  return i >= 0 ? process.argv[i + 1] : fallback;
}

const baseUrl = arg("base-url", "http://127.0.0.1:3141");
const cookie = arg("cookie", "");
const vehicleId = arg("vehicle-id", "");
const outDir = arg("out", "/tmp/lighthouse");
// When set, third-party analytics and the hosting platform's injected script
// are blocked so the audit measures the application's own performance rather
// than the ad-hoc analytics/session-recording that a privacy-respecting
// production config would gate off. See LIGHTHOUSE_EVIDENCE.md.
const blockThirdParty = process.argv.includes("--block-third-party");
const THIRD_PARTY_BLOCK = [
  "*posthog.com*", "*i.posthog.com*", "*assets.emergent.sh*", "*app.emergent.sh*",
];

const host = new URL(baseUrl).hostname;
if (!["127.0.0.1", "localhost"].includes(host)) {
  console.error("Refusing Lighthouse run: target must be local");
  process.exit(2);
}

fs.mkdirSync(outDir, { recursive: true });

// Desktop and mobile emulation profiles matching Lighthouse's own presets,
// except the mobile screen is pinned to the required 360x800 viewport.
const FORM_FACTORS = {
  desktop: {
    formFactor: "desktop",
    screenEmulation: { mobile: false, width: 1440, height: 900, deviceScaleFactor: 1, disabled: false },
    throttling: { rttMs: 40, throughputKbps: 10240, cpuSlowdownMultiplier: 1,
      requestLatencyMs: 0, downloadThroughputKbps: 0, uploadThroughputKbps: 0 },
  },
  mobile: {
    formFactor: "mobile",
    screenEmulation: { mobile: true, width: 360, height: 800, deviceScaleFactor: 2.625, disabled: false },
    throttling: { rttMs: 150, throughputKbps: 1638.4, cpuSlowdownMultiplier: 4,
      requestLatencyMs: 562.5, downloadThroughputKbps: 1474.56, uploadThroughputKbps: 675 },
  },
};

const PAGES = [
  { name: "login", path: "/login", authed: false },
  { name: "dashboard", path: "/dashboard", authed: true },
  { name: "vehicle_list", path: "/vehicles", authed: true },
  { name: "vehicle_profile", path: `/vehicles/${vehicleId}`, authed: true },
];

async function run() {
  const summary = [];
  for (const [ff, ffConfig] of Object.entries(FORM_FACTORS)) {
    for (const page of PAGES) {
      const chrome = await launch({
        chromeFlags: ["--headless=new", "--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage"],
      });
      try {
        const flags = {
          port: chrome.port,
          output: ["json"],
          logLevel: "error",
          onlyCategories: ["performance", "accessibility", "best-practices"],
        };
        if (page.authed && cookie) {
          flags.extraHeaders = { Cookie: `fleet_session=${cookie}` };
        }
        if (blockThirdParty) {
          flags.blockedUrlPatterns = THIRD_PARTY_BLOCK;
        }
        const url = `${baseUrl}${page.path}`;
        const result = await lighthouse(url, flags, { extends: "lighthouse:default", settings: ffConfig });

        const lhr = result.lhr;
        const audits = lhr.audits;
        const row = {
          page: page.name,
          form_factor: ff,
          url,
          performance: Math.round((lhr.categories.performance.score ?? 0) * 100),
          accessibility: Math.round((lhr.categories.accessibility.score ?? 0) * 100),
          best_practices: Math.round((lhr.categories["best-practices"].score ?? 0) * 100),
          cls: audits["cumulative-layout-shift"]?.numericValue ?? null,
          lcp_ms: audits["largest-contentful-paint"]?.numericValue ?? null,
          fcp_ms: audits["first-contentful-paint"]?.numericValue ?? null,
          tbt_ms: audits["total-blocking-time"]?.numericValue ?? null,
        };
        summary.push(row);
        fs.writeFileSync(path.join(outDir, `${page.name}.${ff}.json`), JSON.stringify(lhr));
        console.error(`${ff}/${page.name}: perf=${row.performance} a11y=${row.accessibility} ` +
          `cls=${row.cls?.toFixed(3)} lcp=${Math.round(row.lcp_ms)}ms`);
      } finally {
        await chrome.kill();
      }
    }
  }
  fs.writeFileSync(path.join(outDir, "summary.json"), JSON.stringify(summary, null, 2));
  console.log(JSON.stringify(summary, null, 2));
}

run().catch((err) => { console.error(err); process.exit(1); });
