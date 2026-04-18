/*
 * k6 load test: Deck generation endpoint (/api/v1/generate)
 *
 * TARGET: 100 virtual users, p95 < 30s for async job acceptance
 * The /generate endpoint should respond in < 200ms (it dispatches to Celery).
 *
 * Run: k6 run load-tests/k6/generate_deck.js
 * With env: k6 run -e BASE_URL=http://staging.example.com load-tests/k6/generate_deck.js
 */

import http from 'k6/http';
import { check, sleep } from 'k6';
import { Rate, Trend } from 'k6/metrics';

// Custom metrics
const errorRate = new Rate('errors');
const acceptDuration = new Trend('accept_duration_ms');
const jobCompleteDuration = new Trend('job_complete_duration_ms');

export const options = {
  stages: [
    { duration: '30s', target: 20 },   // Ramp up
    { duration: '2m',  target: 100 },  // Sustained load
    { duration: '30s', target: 0 },    // Ramp down
  ],
  thresholds: {
    http_req_duration: ['p(95)<500'],     // Accept response < 500ms
    errors: ['rate<0.05'],                // < 5% error rate
    accept_duration_ms: ['p(95)<300'],    // Accept latency p95
    job_complete_duration_ms: ['p(95)<30000'], // Full generation p95 < 30s
  },
};

const BASE_URL = __ENV.BASE_URL || 'http://localhost:8000';
const AUTH_TOKEN = __ENV.AUTH_TOKEN || '';

const PROMPTS = [
  'Create a quarterly business review for a SaaS startup in Series B',
  'Design a competitive analysis deck for the cloud infrastructure market',
  'Build a product roadmap presentation for an enterprise AI platform',
  'Prepare investor pitch deck for a fintech company doing $5M ARR',
  'Create an annual board review for a healthcare technology company',
  'Design a digital transformation strategy for a manufacturing firm',
  'Build a market entry analysis for Southeast Asian expansion',
  'Create a customer success metrics dashboard presentation',
  'Prepare a regulatory compliance update for financial services',
  'Design an engineering team OKR review for Q4',
];

const THEMES = [
  'corporate_dark', 'modern_light', 'startup_minimal',
  'healthcare_clinical', 'financial_formal',
];

export default function () {
  const prompt = PROMPTS[Math.floor(Math.random() * PROMPTS.length)];
  const theme = THEMES[Math.floor(Math.random() * THEMES.length)];

  const headers = {
    'Content-Type': 'application/json',
    'Accept-Schema-Version': '1.0.0',
  };
  if (AUTH_TOKEN) {
    headers['Authorization'] = `Bearer ${AUTH_TOKEN}`;
  }

  // Step 1: Submit generation request
  const startTime = Date.now();
  const res = http.post(
    `${BASE_URL}/api/v1/generate`,
    JSON.stringify({
      prompt: prompt,
      theme: theme,
      industry_vertical: 'technology',
    }),
    { headers, timeout: '10s' }
  );

  const acceptTime = Date.now() - startTime;
  acceptDuration.add(acceptTime);

  const accepted = check(res, {
    'status is 200': (r) => r.status === 200,
    'has job_id': (r) => {
      try { return JSON.parse(r.body).job_id !== undefined; }
      catch { return false; }
    },
    'accepted under 500ms': () => acceptTime < 500,
  });

  if (!accepted) {
    errorRate.add(1);
    return;
  }

  errorRate.add(0);
  const jobId = JSON.parse(res.body).job_id;

  // Step 2: Poll until complete (max 60s)
  const pollStart = Date.now();
  let complete = false;
  for (let i = 0; i < 30; i++) {
    sleep(2);
    const pollRes = http.get(`${BASE_URL}/api/v1/job/${jobId}`, { headers });

    if (pollRes.status === 200) {
      try {
        const data = JSON.parse(pollRes.body);
        if (data.status === 'complete' || data.status === 'partial_failure') {
          complete = true;
          jobCompleteDuration.add(Date.now() - pollStart);
          break;
        }
        if (data.status === 'failed') {
          errorRate.add(1);
          break;
        }
      } catch (e) { /* continue polling */ }
    }
  }

  if (!complete) {
    errorRate.add(1);
  }

  sleep(1);
}
