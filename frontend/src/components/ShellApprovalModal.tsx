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
            <ShieldAlert size={16} className="inline mr-2" />
            El agente quiere ejecutar un comando
          </DialogTitle>
          <DialogDescription>
            Revisá el comando antes de aprobarlo. Al aprobarlo, el agente lo
            ejecuta con acceso total al sistema.
          </DialogDescription>
        </DialogHeader>
        <pre className="bg-app-bg-tertiary p-3 rounded-lg overflow-x-auto whitespace-pre-wrap break-all text-sm font-mono text-app-text border border-app-border">
          {approval?.command || ""}
        </pre>
        <div className="flex gap-2 justify-end">
          <button
            type="button"
            disabled={busy}
            onClick={() => void decide(false)}
            className="flex items-center gap-1 bg-app-bg-tertiary text-app-text text-sm font-medium px-4 py-2 rounded-lg hover:bg-app-bg-secondary transition-colors border border-app-border disabled:opacity-40 disabled:cursor-not-allowed"
          >
            <X size={14} /> Denegar
          </button>
          <button
            type="button"
            disabled={busy}
            onClick={() => void decide(true)}
            className="flex items-center gap-1 bg-app-bg-tertiary text-app-text text-sm font-medium px-4 py-2 rounded-lg hover:bg-app-bg-secondary transition-colors border border-app-border disabled:opacity-40 disabled:cursor-not-allowed"
          >
            <Check size={14} /> Aprobar
          </button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
