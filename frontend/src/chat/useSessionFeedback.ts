import { useCallback, useEffect, useState } from "react";
import feedbackService, {
  type FeedbackType,
  type SessionFeedback,
} from "../services/feedbackService";

/**
 * Thumbs up / down of the answers of a session, keyed by turn number.
 *
 * Loads the session's feedback when the session changes. `vote` saves the
 * feedback right away in the UI and rolls it back if the backend fails;
 * clicking the same thumb again removes it.
 */
export function useSessionFeedback(sessionId: string | null) {
  const [feedback, setFeedback] = useState<SessionFeedback>({});

  useEffect(() => {
    setFeedback({});
    if (!sessionId) return;
    let cancelled = false;
    feedbackService
      .getSessionFeedback(sessionId)
      .then((data) => {
        if (!cancelled) setFeedback(data);
      })
      .catch((err) => console.error("Error cargando feedback:", err));
    return () => {
      cancelled = true;
    };
  }, [sessionId]);

  const vote = useCallback(
    async (turn: number, type: FeedbackType) => {
      if (!sessionId) return;
      const previous = feedback[turn];
      const next = previous === type ? undefined : type;
      const apply = (value: FeedbackType | undefined) =>
        setFeedback((prev) => {
          const updated = { ...prev };
          if (value) updated[turn] = value;
          else delete updated[turn];
          return updated;
        });

      apply(next);
      try {
        if (next) await feedbackService.setFeedback(sessionId, turn, next);
        else await feedbackService.clearFeedback(sessionId, turn);
      } catch (err) {
        console.error("Error guardando feedback:", err);
        apply(previous);
      }
    },
    [sessionId, feedback],
  );

  return { feedback, vote };
}
