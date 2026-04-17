'use client'

import { useParams } from 'next/navigation'
import { DeckCanvas } from '../../components/editor/DeckCanvas'

export default function DeckPage() {
  const params = useParams()
  const jobId = params.jobId as string

  if (!jobId) {
    return <div className="p-8">No job ID provided</div>
  }

  return <DeckCanvas jobId={jobId} />
}
