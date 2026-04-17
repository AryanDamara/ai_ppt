'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import { v4 as uuidv4 } from 'uuid'
import { validateGenerateRequest } from '../../lib/schema-validator'
import { useDeckStore } from '../../hooks/useDeckStore'

const THEMES = [
  { value: 'modern_light', label: 'Modern Light' },
  { value: 'corporate_dark', label: 'Corporate Dark' },
  { value: 'startup_minimal', label: 'Startup Minimal' },
  { value: 'healthcare_clinical', label: 'Healthcare Clinical' },
  { value: 'financial_formal', label: 'Financial Formal' },
]

export function PromptInput() {
  const router = useRouter()
  const { setJobId, reset } = useDeckStore()

  const [prompt, setPrompt] = useState('')
  const [theme, setTheme] = useState('modern_light')
  const [loading, setLoading] = useState(false)
  const [validationErrors, setValidationErrors] = useState<string[]>([])

  const handleSubmit = async () => {
    // Step 1: Optimistic UI — show loading immediately
    setLoading(true)
    setValidationErrors([])

    // Step 2: Client-side validation BEFORE hitting the API
    const clientRequestId = uuidv4()
    const requestData = { prompt, theme, client_request_id: clientRequestId }
    const validation = validateGenerateRequest(requestData)

    if (!validation.success) {
      setValidationErrors(validation.errors)
      setLoading(false)
      return
    }

    try {
      reset()  // Clear any previous generation state

      const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/api/v1/generate`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Accept-Schema-Version': '1.0.0',
          'X-Request-ID': uuidv4(),
        },
        body: JSON.stringify(validation.data),
      })

      if (!res.ok) {
        const err = await res.json()
        throw new Error(err.detail || `HTTP ${res.status}`)
      }

      const { job_id } = await res.json()
      setJobId(job_id)
      router.push(`/deck/${job_id}`)

    } catch (error) {
      setValidationErrors([(error as Error).message])
      setLoading(false)
    }
  }

  return (
    <div className="max-w-2xl mx-auto mt-16 px-4">
      <h1 className="text-2xl font-semibold text-gray-900 mb-6">
        Generate a presentation
      </h1>

      <textarea
        value={prompt}
        onChange={(e) => setPrompt(e.target.value)}
        placeholder="Describe your presentation... e.g. 'Create a pitch deck for a B2B SaaS company targeting enterprise HR teams'"
        className="w-full h-32 p-4 border border-gray-300 rounded-lg text-sm resize-none focus:outline-none focus:ring-2 focus:ring-blue-500"
        maxLength={2000}
        disabled={loading}
      />

      <div className="flex items-center gap-4 mt-3">
        <select
          value={theme}
          onChange={(e) => setTheme(e.target.value)}
          className="border border-gray-300 rounded-lg px-3 py-2 text-sm"
          disabled={loading}
        >
          {THEMES.map((t) => (
            <option key={t.value} value={t.value}>{t.label}</option>
          ))}
        </select>

        <button
          onClick={handleSubmit}
          disabled={loading || prompt.length < 10}
          className="ml-auto px-6 py-2 bg-gray-900 text-white text-sm font-medium rounded-lg
                     disabled:opacity-50 disabled:cursor-not-allowed hover:bg-gray-700 transition-colors"
        >
          {loading ? 'Starting...' : 'Generate'}
        </button>
      </div>

      {validationErrors.length > 0 && (
        <div className="mt-3 p-3 bg-red-50 border border-red-200 rounded-lg">
          {validationErrors.map((err, i) => (
            <p key={i} className="text-red-600 text-sm">{err}</p>
          ))}
        </div>
      )}

      <p className="text-xs text-gray-400 mt-2">
        {prompt.length}/2000 characters
      </p>
    </div>
  )
}
