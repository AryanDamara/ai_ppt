"use client";

import { useEffect, useRef } from "react";
import { trackEditEvent } from "@/lib/telemetry";

interface EditTelemetryProps {
  deckId: string;
  slideId: string;
  elementId: string;
  elementType: string;
  traceId?: string;
}

/**
 * Hook-style component for tracking user edits to slide content.
 * Wraps around an editable element and emits edit events (debounced, anonymised).
 *
 * Usage:
 *   <EditTelemetry deckId="..." slideId="..." elementId="..." elementType="bullet" />
 *   <input onChange={...} />
 */
export function useEditTelemetry(config: EditTelemetryProps) {
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const lastValueRef = useRef<string>("");

  const onEdit = (newValue: string) => {
    // Debounce: only send after 2 seconds of inactivity
    if (timerRef.current) {
      clearTimeout(timerRef.current);
    }

    timerRef.current = setTimeout(() => {
      const original = lastValueRef.current;
      if (original === newValue) return;

      trackEditEvent({
        deckId: config.deckId,
        slideId: config.slideId,
        elementId: config.elementId,
        elementType: config.elementType,
        originalValue: original,
        newValue: newValue,
        traceId: config.traceId,
      });

      lastValueRef.current = newValue;
    }, 2000);
  };

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (timerRef.current) {
        clearTimeout(timerRef.current);
      }
    };
  }, []);

  return { onEdit, setInitialValue: (v: string) => { lastValueRef.current = v; } };
}
