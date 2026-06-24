/**
 * SoroScan k6 smoke load test.
 *
 * Lightweight CI-friendly probe of core unauthenticated endpoints.
 */
import http from "k6/http";
import { check, sleep } from "k6";
import { textSummary } from "https://jslib.k6.io/k6-summary/0.0.2/index.js";

export const options = {
  vus: Number(__ENV.K6_VUS || 5),
  duration: __ENV.K6_DURATION || "30s",
  thresholds: {
    http_req_failed: ["rate<0.01"],
    http_req_duration: ["p(95)<2000"],
  },
};

const BASE_URL = __ENV.BASE_URL || "http://127.0.0.1:8000";

export default function () {
  const health = http.get(`${BASE_URL}/api/ingest/health/`, {
    tags: { name: "health" },
  });
  check(health, {
    "health status is 200": (res) => res.status === 200,
    "health payload ok": (res) => res.json("status") === "healthy",
  });

  const ready = http.get(`${BASE_URL}/ready/`, {
    tags: { name: "ready" },
    responseCallback: http.expectedStatuses(200, 503),
  });
  check(ready, {
    "readiness endpoint reachable": (res) => [200, 503].includes(res.status),
  });

  sleep(1);
}

export function handleSummary(data) {
  const reportPath = __ENV.K6_REPORT_PATH || "load-tests/results/smoke-summary.json";
  return {
    stdout: textSummary(data, { indent: " ", enableColors: true }),
    [reportPath]: JSON.stringify(data, null, 2),
  };
}
