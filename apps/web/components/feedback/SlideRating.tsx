"use client";

import React, { useState } from "react";
import { authedFetch } from "@/lib/supabase";

interface SlideRatingProps {
  deckId: string;
  slideId: string;
  traceId?: string;
  onFeedbackSent?: (type: "thumbs_up" | "thumbs_down") => void;
}

/**
 * Thumbs up/down feedback component for individual slides.
 * Sends feedback to POST /api/v1/feedback with the JWT token.
 */
export function SlideRating({
  deckId,
  slideId,
  traceId,
  onFeedbackSent,
}: SlideRatingProps) {
  const [sent, setSent] = useState<"thumbs_up" | "thumbs_down" | null>(null);
  const [sending, setSending] = useState(false);

  const sendFeedback = async (type: "thumbs_up" | "thumbs_down") => {
    if (sent || sending) return;
    setSending(true);

    try {
      const apiUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
      await authedFetch(`${apiUrl}/api/v1/feedback`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          deck_id: deckId,
          slide_id: slideId,
          feedback_type: type,
          trace_id: traceId,
        }),
      });

      setSent(type);
      onFeedbackSent?.(type);
    } catch (err) {
      console.error("Feedback failed:", err);
    } finally {
      setSending(false);
    }
  };

  return (
    <div className="flex items-center gap-2">
      <button
        onClick={() => sendFeedback("thumbs_up")}
        disabled={sent !== null || sending}
        className={`flex items-center gap-1 rounded-lg px-3 py-1.5 text-xs font-medium transition-all ${
          sent === "thumbs_up"
            ? "border border-green-500/30 bg-green-500/10 text-green-400"
            : "border border-gray-600/50 bg-gray-700/30 text-gray-400 hover:border-green-500/50 hover:text-green-400"
        }`}
        id={`slide-rating-up-${slideId}`}
        aria-label="Thumbs up for this slide"
      >
        <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M14 10h4.764a2 2 0 011.789 2.894l-3.5 7A2 2 0 0115.263 21h-4.017c-.163 0-.326-.02-.485-.06L7 20m7-10V5a2 2 0 00-2-2h-.095c-.5 0-.905.405-.905.905 0 .714-.211 1.412-.608 2.006L7 11v9m7-10h-2M7 20H5a2 2 0 01-2-2v-6a2 2 0 012-2h2.5"
          />
        </svg>
        {sent === "thumbs_up" ? "Thanks!" : "Good"}
      </button>

      <button
        onClick={() => sendFeedback("thumbs_down")}
        disabled={sent !== null || sending}
        className={`flex items-center gap-1 rounded-lg px-3 py-1.5 text-xs font-medium transition-all ${
          sent === "thumbs_down"
            ? "border border-red-500/30 bg-red-500/10 text-red-400"
            : "border border-gray-600/50 bg-gray-700/30 text-gray-400 hover:border-red-500/50 hover:text-red-400"
        }`}
        id={`slide-rating-down-${slideId}`}
        aria-label="Thumbs down for this slide"
      >
        <svg className="h-4 w-4 rotate-180" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M14 10h4.764a2 2 0 011.789 2.894l-3.5 7A2 2 0 0115.263 21h-4.017c-.163 0-.326-.02-.485-.06L7 20m7-10V5a2 2 0 00-2-2h-.095c-.5 0-.905.405-.905.905 0 .714-.211 1.412-.608 2.006L7 11v9m7-10h-2M7 20H5a2 2 0 01-2-2v-6a2 2 0 012-2h2.5"
          />
        </svg>
        {sent === "thumbs_down" ? "Noted" : "Bad"}
      </button>

      {sending && (
        <div className="h-4 w-4 animate-spin rounded-full border-2 border-gray-500 border-t-transparent" />
      )}
    </div>
  );
}
