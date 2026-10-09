/**
 * Shared infrastructure endpoints (settings, cache, health). These are
 * not part of the product workbench; they live in app.py alongside the
 * run lifecycle and are exposed here so the few frontend callers that
 * need them don't reach for the legacy `client.ts` shape.
 */
import type { Settings } from '@/types'

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, init)
  if (!res.ok) {
    let detail = ''
    try {
      const body = await res.json()
      detail = body?.detail ?? ''
    } catch {
      // ignore non-JSON error bodies
    }
    throw new Error(detail || `请求失败（${res.status}）`)
  }
  return res.json() as Promise<T>
}

export interface SaveLlmResult {
  ok: boolean
  configured: boolean
  api_key_set: boolean
  base_url: string
  input_price_per_million: number | null
  output_price_per_million: number | null
}

export interface TestLlmResult {
  ok: boolean
  model: string
  latency_ms: number
  usage?: { total_tokens?: number }
}

export interface ClearCacheResult {
  ok: boolean
  removed: string[]
}

export interface HealthResult {
  ok: boolean
  llm_configured: boolean
  zhiyun_live_configured: boolean
}

export const infrastructureApi = {
  health: () => request<HealthResult>('/api/health'),
  settings: () => request<Settings>('/api/settings'),
  saveLlm: (
    base_url: string,
    model: string,
    api_key: string,
    input_price_per_million?: number,
    output_price_per_million?: number,
  ) =>
    request<SaveLlmResult>('/api/settings/llm', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ base_url, model, api_key, input_price_per_million, output_price_per_million }),
    }),
  testLlm: () =>
    request<TestLlmResult>('/api/settings/llm/test', {
      method: 'POST',
    }),
  clearCache: () =>
    request<ClearCacheResult>('/api/cache', { method: 'DELETE' }),
}
