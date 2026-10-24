import { useCallback, useState } from "react";
import { API_BASE_URL } from "../config/api";

/** Creator kind: selects the `/api/create/<kind>/verify` endpoint. */
export type CreatorKind = "agent" | "skill" | "tool" | "workflow";

/** Verdict shown in the toast under the composer. */
export interface VerifyToast {
  done: boolean;
  reason: string;
}

interface VerifyResponse {
  status: string;
  message?: string;
  data?: { done?: boolean };
}

/**
 * Shared verification logic for the four creator pages.
 *
 * Calls the decision model (or LLM fallback) through the creator
 * ``verify`` endpoint and stores the verdict in a toast state.
 *
 * @param kind Creator page using the hook (selects the endpoint).
 * @returns The running flag, the toast to render, and the trigger.
 */
export function useCreatorVerify(kind: CreatorKind) {
  const [verifying, setVerifying] = useState(false);
  const [verifyToast, setVerifyToast] = useState<VerifyToast | null>(null);

  const verificar = useCallback(
    async (creatorId: string, blocked: boolean) => {
      if (verifying || blocked) return;
      setVerifying(true);
      setVerifyToast(null);
      try {
        const res = await fetch(`${API_BASE_URL}/api/create/${kind}/verify`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ creator_id: creatorId }),
        });
        const json: VerifyResponse = await res.json();
        if (json.status === "success" && json.data) {
          setVerifyToast({ done: !!json.data.done, reason: json.message || "" });
        } else {
          setVerifyToast({ done: false, reason: json.message || "No se pudo verificar." });
        }
      } catch (err) {
        setVerifyToast({ done: false, reason: err instanceof Error ? err.message : "Error de conexión." });
      } finally {
        setVerifying(false);
      }
    },
    [verifying, kind],
  );

  return { verifying, verifyToast, verificar };
}

/**
 * Toast banner rendering the verification verdict.
 *
 * @param props Props holding the toast to render (null renders nothing).
 * @returns The banner element or null.
 */
export function VerifyToastBanner({ toast }: { toast: VerifyToast | null }) {
  if (!toast) return null;
  return (
    <div className={`mb-2 text-sm rounded-lg px-4 py-2.5 border ${toast.done ? "text-green-700 bg-green-50 border-green-200" : "text-amber-700 bg-amber-50 border-amber-200"}`}>
      <span className="font-medium">{toast.done ? "Verificación: cumple." : "Verificación: no cumple."}</span>
      {toast.reason && <span> {toast.reason}</span>}
    </div>
  );
}
