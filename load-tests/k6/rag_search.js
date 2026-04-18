/*
 * k6 load test: RAG search endpoint
 *
 * TARGET: 200 VU, p95 < 2s for search queries
 *
 * Run: k6 run load-tests/k6/rag_search.js
 */

import http from 'k6/http';
import { check, sleep } from 'k6';
import { Rate, Trend } from 'k6/metrics';

const errorRate = new Rate('errors');
const searchDuration = new Trend('search_duration_ms');

export const options = {
  stages: [
    { duration: '15s', target: 50 },
    { duration: '1m',  target: 200 },
    { duration: '15s', target: 0 },
  ],
  thresholds: {
    http_req_duration: ['p(95)<2000'],
    errors: ['rate<0.05'],
    search_duration_ms: ['p(95)<2000'],
  },
};

const BASE_URL = __ENV.BASE_URL || 'http://localhost:8001';
const AUTH_TOKEN = __ENV.AUTH_TOKEN || '';
const TENANT_ID = __ENV.TENANT_ID || 'test-tenant-001';

const QUERIES = [
  'revenue growth trends in Q3',
  'customer acquisition cost breakdown',
  'market share by region',
  'product roadmap milestones',
  'competitive landscape analysis',
  'employee engagement survey results',
  'supply chain optimization metrics',
  'digital transformation KPIs',
  'regulatory compliance requirements',
  'financial projections for next year',
];

export default function () {
  const query = QUERIES[Math.floor(Math.random() * QUERIES.length)];

  const headers = {
    'Content-Type': 'application/json',
  };
  if (AUTH_TOKEN) {
    headers['Authorization'] = `Bearer ${AUTH_TOKEN}`;
  }

  const startTime = Date.now();
  const res = http.post(
    `${BASE_URL}/api/v1/search`,
    JSON.stringify({
      query: query,
      tenant_id: TENANT_ID,
      top_k: 5,
    }),
    { headers, timeout: '5s' }
  );

  searchDuration.add(Date.now() - startTime);

  check(res, {
    'status is 200': (r) => r.status === 200,
    'has results': (r) => {
      try { return JSON.parse(r.body).results !== undefined; }
      catch { return false; }
    },
    'search under 2s': () => (Date.now() - startTime) < 2000,
  });

  errorRate.add(res.status >= 400 ? 1 : 0);
  sleep(0.5);
}
