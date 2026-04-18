/*
 * k6 load test: PPTX export endpoint
 *
 * TARGET: 50 VU, p95 < 10s for export triggers
 *
 * Run: k6 run load-tests/k6/export_pptx.js
 */

import http from 'k6/http';
import { check, sleep } from 'k6';
import { Rate, Trend } from 'k6/metrics';

const errorRate = new Rate('errors');
const exportDuration = new Trend('export_duration_ms');

export const options = {
  stages: [
    { duration: '20s', target: 10 },
    { duration: '1m',  target: 50 },
    { duration: '20s', target: 0 },
  ],
  thresholds: {
    http_req_duration: ['p(95)<10000'],
    errors: ['rate<0.1'],
  },
};

const BASE_URL = __ENV.BASE_URL || 'http://localhost:8000';
const AUTH_TOKEN = __ENV.AUTH_TOKEN || '';
const DECK_ID = __ENV.DECK_ID || 'test-deck-001';

export default function () {
  const headers = {
    'Content-Type': 'application/json',
  };
  if (AUTH_TOKEN) {
    headers['Authorization'] = `Bearer ${AUTH_TOKEN}`;
  }

  const startTime = Date.now();
  const res = http.post(
    `${BASE_URL}/api/v1/deck/${DECK_ID}/export`,
    JSON.stringify({ plan_tier: 'pro' }),
    { headers, timeout: '30s' }
  );

  exportDuration.add(Date.now() - startTime);

  check(res, {
    'status is 200 or 404': (r) => r.status === 200 || r.status === 404,
  });

  errorRate.add(res.status >= 500 ? 1 : 0);
  sleep(2);
}
