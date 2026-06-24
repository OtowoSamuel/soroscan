/**
 * SoroScan k6 scenario suite for primary API workflows.
 */
import http from "k6/http";
import { check, group, sleep } from "k6";
import { textSummary } from "https://jslib.k6.io/k6-summary/0.0.2/index.js";

export const options = {
  scenarios: {
    browse_contracts: {
      executor: "constant-vus",
      vus: Number(__ENV.K6_CONTRACT_VUS || 3),
      duration: __ENV.K6_DURATION || "45s",
      exec: "browseContracts",
    },
    query_events: {
      executor: "constant-vus",
      vus: Number(__ENV.K6_EVENT_VUS || 3),
      duration: __ENV.K6_DURATION || "45s",
      exec: "queryEvents",
      startTime: "5s",
    },
  },
  thresholds: {
    http_req_failed: ["rate<0.1"],
    "http_req_duration{scenario:browse_contracts}": ["p(95)<3000"],
    "http_req_duration{scenario:query_events}": ["p(95)<3000"],
  },
};

const BASE_URL = __ENV.BASE_URL || "http://127.0.0.1:8000";

export function browseContracts() {
  group("list contracts", () => {
    const res = http.get(`${BASE_URL}/api/ingest/contracts/`);
    check(res, {
      "contracts list responds": (r) => r.status === 200 || r.status === 401,
    });
  });
  sleep(1);
}

export function queryEvents() {
  group("graphql events query", () => {
    const res = http.post(
      `${BASE_URL}/graphql/`,
      JSON.stringify({
        query: "{ events(first: 10) { id eventType ledger } }",
      }),
      { headers: { "Content-Type": "application/json" } }
    );
    check(res, {
      "events query responds": (r) => r.status === 200,
    });
  });
  sleep(1);
}

export function handleSummary(data) {
  const reportPath =
    __ENV.K6_REPORT_PATH || "load-tests/results/scenarios-summary.json";
  return {
    stdout: textSummary(data, { indent: " ", enableColors: true }),
    [reportPath]: JSON.stringify(data, null, 2),
  };
}
