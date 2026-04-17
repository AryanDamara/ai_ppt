import { create } from 'zustand'
import type { Slide, PresentationDeck, GenerationStatus } from '../types/deck'

interface FailedSlot {
  slideIndex: number
  slideType: string
  error: string
  retryId: string
}

interface DeckStore {
  deck: PresentationDeck | null
  slides: Slide[]           // ALWAYS sorted by slide_index
  failedSlots: FailedSlot[]
  generationStatus: GenerationStatus
  error: string | null
  jobId: string | null
  setJobId: (jobId: string) => void
  addSlide: (slide: Slide) => void
  markSlideAsFailed: (slot: FailedSlot) => void
  setDeck: (deck: PresentationDeck) => void
  setGenerationStatus: (status: GenerationStatus) => void
  setError: (error: string | null) => void
  updateSlide: (slideId: string, updates: Partial<Slide>) => void
  reset: () => void
}

export const useDeckStore = create<DeckStore>((set) => ({
  deck: null,
  slides: [],
  failedSlots: [],
  generationStatus: 'draft',
  error: null,
  jobId: null,

  setJobId: (jobId) => set({ jobId }),

  addSlide: (slide) =>
    set((state) => ({
      slides: [
        ...state.slides.filter((s) => s.slide_id !== slide.slide_id),
        slide,
      ].sort((a, b) => a.slide_index - b.slide_index),  // Always sort by slide_index
    })),

  markSlideAsFailed: (slot) =>
    set((state) => ({
      failedSlots: [
        ...state.failedSlots.filter((f) => f.slideIndex !== slot.slideIndex),
        slot,
      ],
    })),

  setDeck: (deck) =>
    set({
      deck,
      slides: [...deck.slides].sort((a, b) => a.slide_index - b.slide_index),
    }),

  setGenerationStatus: (status) => set({ generationStatus: status }),
  setError: (error) => set({ error }),

  updateSlide: (slideId, updates) =>
    set((state) => ({
      slides: state.slides.map((s) =>
        s.slide_id === slideId ? { ...s, ...updates } : s
      ),
    })),

  reset: () =>
    set({ deck: null, slides: [], failedSlots: [], generationStatus: 'draft', error: null, jobId: null }),
}))
