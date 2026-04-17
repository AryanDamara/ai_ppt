/**
 * useUndoManager — React hook for layout undo/redo functionality.
 */

import { useState, useCallback, useEffect } from 'react'
import { undoManager, LayoutCommand } from '../lib/layout/undo-manager'

export function useUndoManager() {
  const [canUndo, setCanUndo] = useState(false)
  const [canRedo, setCanRedo] = useState(false)
  const [undoDescription, setUndoDescription] = useState<string | null>(null)
  const [redoDescription, setRedoDescription] = useState<string | null>(null)

  // Update state from undoManager
  const updateState = useCallback(() => {
    setCanUndo(undoManager.canUndo())
    setCanRedo(undoManager.canRedo())
    setUndoDescription(undoManager.getUndoDescription())
    setRedoDescription(undoManager.getRedoDescription())
  }, [])

  // Execute a command
  const execute = useCallback(async (command: LayoutCommand) => {
    await undoManager.execute(command)
    updateState()
  }, [updateState])

  // Undo last command
  const undo = useCallback(async () => {
    const success = await undoManager.undo()
    updateState()
    return success
  }, [updateState])

  // Redo last undone command
  const redo = useCallback(async () => {
    const success = await undoManager.redo()
    updateState()
    return success
  }, [updateState])

  // Clear history
  const clear = useCallback(() => {
    undoManager.clear()
    updateState()
  }, [updateState])

  // Keyboard shortcuts
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      // Ctrl/Cmd + Z
      if ((e.ctrlKey || e.metaKey) && e.key === 'z' && !e.shiftKey) {
        e.preventDefault()
        undo()
      }
      // Ctrl/Cmd + Shift + Z or Ctrl/Cmd + Y
      if ((e.ctrlKey || e.metaKey) && (e.key === 'y' || (e.key === 'z' && e.shiftKey))) {
        e.preventDefault()
        redo()
      }
    }

    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [undo, redo])

  return {
    canUndo,
    canRedo,
    undoDescription,
    redoDescription,
    execute,
    undo,
    redo,
    clear,
  }
}

export default useUndoManager