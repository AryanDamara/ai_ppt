/**
 * Module 9 — Autosave & Crash Recovery
 * IndexedDB-based autosave for layout solutions.
 */

import { openDB, IDBPDatabase } from 'idb'
import type { FrontendLayoutSolution } from './types'

const DB_NAME = 'aippt-autosave'
const STORE_NAME = 'layout-snapshots'
const SCHEMA_VERSION = 1
const AUTOSAVE_TTL_MS = 48 * 60 * 60 * 1000  // 48 hours

interface LayoutSnapshot {
  deckId: string
  schemaVersion: string
  solutions: Record<string, FrontendLayoutSolution>
  savedAt: number
}

async function getDB(): Promise<IDBPDatabase> {
  return openDB(DB_NAME, SCHEMA_VERSION, {
    upgrade(db) {
      if (!db.objectStoreNames.contains(STORE_NAME)) {
        db.createObjectStore(STORE_NAME, { keyPath: 'deckId' })
      }
    },
  })
}

export async function saveLayoutSnapshot(
  deckId: string,
  solutions: Record<string, FrontendLayoutSolution>,
): Promise<void> {
  try {
    const db = await getDB()
    const snapshot: LayoutSnapshot = {
      deckId,
      schemaVersion: '1.0.0',
      solutions,
      savedAt: Date.now(),
    }
    await db.put(STORE_NAME, snapshot)
  } catch (error) {
    // Autosave failure is non-fatal — log and continue
    console.warn('[Autosave] Failed to save layout snapshot:', error)
  }
}

export async function recoverLayoutSnapshot(
  deckId: string,
): Promise<Record<string, FrontendLayoutSolution> | null> {
  try {
    const db = await getDB()
    const snapshot = await db.get(STORE_NAME, deckId) as LayoutSnapshot | undefined

    if (!snapshot) return null

    // Check TTL
    if (Date.now() - snapshot.savedAt > AUTOSAVE_TTL_MS) {
      await db.delete(STORE_NAME, deckId)
      return null
    }

    return snapshot.solutions
  } catch (error) {
    console.warn('[Autosave] Failed to recover layout snapshot:', error)
    return null
  }
}

export async function clearLayoutSnapshot(deckId: string): Promise<void> {
  try {
    const db = await getDB()
    await db.delete(STORE_NAME, deckId)
  } catch {
    // Non-fatal
  }
}

/**
 * Set up automatic autosave triggers.
 * Call once when DeckCanvas mounts.
 */
export function setupAutosave(
  deckId: string,
  getSolutions: () => Record<string, FrontendLayoutSolution>,
): () => void {
  let intervalId: ReturnType<typeof setInterval>

  // Save every 30 seconds
  intervalId = setInterval(() => {
    saveLayoutSnapshot(deckId, getSolutions())
  }, 30_000)

  // Save when tab becomes hidden (user navigating away)
  const handleVisibilityChange = () => {
    if (document.visibilityState === 'hidden') {
      saveLayoutSnapshot(deckId, getSolutions())
    }
  }
  document.addEventListener('visibilitychange', handleVisibilityChange)

  // Save before unload
  const handleBeforeUnload = () => {
    saveLayoutSnapshot(deckId, getSolutions())
  }
  window.addEventListener('beforeunload', handleBeforeUnload)

  // Return cleanup function for useEffect
  return () => {
    clearInterval(intervalId)
    document.removeEventListener('visibilitychange', handleVisibilityChange)
    window.removeEventListener('beforeunload', handleBeforeUnload)
  }
}