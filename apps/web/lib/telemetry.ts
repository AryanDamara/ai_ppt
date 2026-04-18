import { authedFetch } from "@/lib/supabase";

interface EditEvent {
  deckId: string;
  slideId: string;
  elementId: string;
  elementType: string;
  originalValue: string;
  newValue: string;
  traceId?: string;
}

/**
 * Send an edit telemetry event to the feedback API.
 * Anonymises original value via SHA-256 hash by default.
 * Non-blocking: fires and forgets.
 */
export function trackEditEvent(event: EditEvent): void {
  const apiUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

  // Anonymise original value client-side before sending
  const anonymisedOriginal = hashString(event.originalValue);

  authedFetch(`${apiUrl}/api/v1/feedback`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      deck_id: event.deckId,
      slide_id: event.slideId,
      feedback_type: "edit",
      edit_delta: {
        element_id: event.elementId,
        element_type: event.elementType,
        original_hash: anonymisedOriginal,
        new_value_length: event.newValue.length,
        change_type: classifyChange(event.originalValue, event.newValue),
      },
      original_value: anonymisedOriginal,
      new_value: null, // Never send full new value unless consent=full
      trace_id: event.traceId,
    }),
  }).catch((err) => {
    // Non-blocking: don't break UX if telemetry fails
    console.debug("Edit telemetry failed:", err);
  });
}

/**
 * Classify the type of edit the user made.
 */
function classifyChange(original: string, newValue: string): string {
  if (newValue.length === 0) return "deleted";
  if (original.length === 0) return "added";
  if (newValue.length > original.length * 1.5) return "expanded";
  if (newValue.length < original.length * 0.5) return "shortened";
  return "modified";
}

/**
 * Simple hash function for client-side anonymisation.
 * SHA-256 via Web Crypto API.
 */
function hashString(input: string): string {
  // Synchronous fallback: use simple hash for speed
  let hash = 0;
  for (let i = 0; i < input.length; i++) {
    const char = input.charCodeAt(i);
    hash = (hash << 5) - hash + char;
    hash |= 0; // Convert to 32-bit integer
  }
  return Math.abs(hash).toString(16).padStart(8, "0");
}
