import { useEffect, useRef, useState } from "react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "./ui/dialog";
import { ShieldAlert, Check, X } from "lucide-react";
import approvalService from "../services/approvalService";

export interface PendingShellApproval {
  approval_id: string;
  command: string;
}

interface ShellApprovalModalProps {
  approval: PendingShellApproval | null;
  onResolved: () => void;
}

/** Modal that asks the user to approve or deny a shell command. */
export function ShellApprovalModal({ approval, onResolved }: ShellApprovalModalProps) {
  const [busy, setBusy] = useState(false);
  // Guards the ghost-deny: Dialog closing after an explicit decision must
  // not fire a second resolve. Reset per approval so the next modal works.
  const decidedRef = useRef(false);
  useEffect(() => {
    decidedRef.current = false;
    setBusy(false);
  }, [approval?.approval_id]);

  async function decide(approved: boolean): Promise<void> {
    if (!approval || busy || decidedRef.current) return;
    decidedRef.current = true;
    setBusy(true);
    try {
      await approvalService.resolve(approval.approval_id, approved);
    } catch {
      // The approval may have timed out server-side; closing anyway.
    } finally {
      setBusy(false);
      onResolved();
    }
  }

  return (
    <Dialog open={approval !== null} onOpenChange={(open) => { if (!open) void decide(false); }}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>
            <ShieldAlert size={16} style={{ display: "inline", marginRight: 8 }} />
            El agente quiere ejecutar un comando
          </DialogTitle>
          <DialogDescription>
            Revisá el comando antes de aprobarlo. Al aprobarlo, el agente lo
            ejecuta con acceso total al sistema.
          </DialogDescription>
        </DialogHeader>
        <pre
          style={{
            background: "var(--muted, #f4f4f5)",
            padding: 12,
            borderRadius: 8,
            overflowX: "auto",
            whiteSpace: "pre-wrap",
            wordBreak: "break-all",
          }}
        >
          {approval?.command || ""}
        </pre>
        <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
          <button
            type="button"
            disabled={busy}
            onClick={() => void decide(false)}
            style={{ display: "flex", alignItems: "center", gap: 6 }}
          >
            <X size={14} /> Denegar
          </button>
          <button
            type="button"
            disabled={busy}
            onClick={() => void decide(true)}
            style={{ display: "flex", alignItems: "center", gap: 6 }}
          >
            <Check size={14} /> Aprobar
          </button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
