/**
 * Module 7 — Undo/Redo Command Pattern
 * Every user-initiated layout change is wrapped in a LayoutCommand.
 */

import type { FrontendLayoutSolution } from './types'

const MAX_HISTORY_LENGTH = 50

export interface LayoutCommand {
  execute(): Promise<void>
  undo(): Promise<void>
  getDescription(): string
}

export class MoveElementCommand implements LayoutCommand {
  constructor(
    private slideId: string,
    private elementId: string,
    private previousBounds: { x: number; y: number; width: number; height: number },
    private newBounds: { x: number; y: number; width: number; height: number },
    private applyBounds: (slideId: string, elementId: string, bounds: typeof this.newBounds) => Promise<void>
  ) {}

  async execute() {
    await this.applyBounds(this.slideId, this.elementId, this.newBounds)
  }

  async undo() {
    await this.applyBounds(this.slideId, this.elementId, this.previousBounds)
  }

  getDescription() {
    return `Moved element on slide`
  }
}

export class UpdateBulletTextCommand implements LayoutCommand {
  constructor(
    private slideId: string,
    private elementId: string,
    private previousText: string,
    private newText: string,
    private updateText: (slideId: string, elementId: string, text: string) => Promise<void>
  ) {}

  async execute() {
    await this.updateText(this.slideId, this.elementId, this.newText)
  }

  async undo() {
    await this.updateText(this.slideId, this.elementId, this.previousText)
  }

  getDescription() {
    return `Edit bullet text`
  }
}

export class ResizeElementCommand implements LayoutCommand {
  constructor(
    private slideId: string,
    private elementId: string,
    private previousSize: { width: number; height: number },
    private newSize: { width: number; height: number },
    private applySize: (slideId: string, elementId: string, size: typeof this.newSize) => Promise<void>
  ) {}

  async execute() {
    await this.applySize(this.slideId, this.elementId, this.newSize)
  }

  async undo() {
    await this.applySize(this.slideId, this.elementId, this.previousSize)
  }

  getDescription() {
    return `Resized element`
  }
}

export class UndoManager {
  private undoStack: LayoutCommand[] = []
  private redoStack: LayoutCommand[] = []

  async execute(command: LayoutCommand): Promise<void> {
    await command.execute()
    this.undoStack.push(command)
    this.redoStack = []

    // Bound history length
    if (this.undoStack.length > MAX_HISTORY_LENGTH) {
      this.undoStack.shift()
    }
  }

  async undo(): Promise<boolean> {
    const command = this.undoStack.pop()
    if (!command) return false
    await command.undo()
    this.redoStack.push(command)
    return true
  }

  async redo(): Promise<boolean> {
    const command = this.redoStack.pop()
    if (!command) return false
    await command.execute()
    this.undoStack.push(command)
    return true
  }

  canUndo(): boolean { return this.undoStack.length > 0 }
  canRedo(): boolean { return this.redoStack.length > 0 }

  getUndoDescription(): string | null {
    return this.undoStack.at(-1)?.getDescription() ?? null
  }

  getRedoDescription(): string | null {
    return this.redoStack.at(-1)?.getDescription() ?? null
  }

  clear(): void {
    this.undoStack = []
    this.redoStack = []
  }
}

// Singleton accessible across the app
export const undoManager = new UndoManager()