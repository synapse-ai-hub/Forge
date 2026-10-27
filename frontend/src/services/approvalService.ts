import { API_BASE_URL } from "../config/api";

const approvalService = {
  /** Resolve a pending shell approval with the user's decision. */
  async resolve(approvalId: string, approved: boolean): Promise<void> {
    const response = await fetch(
      `${API_BASE_URL}/api/approvals/${approvalId}/resolve`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ approved }),
      },
    );
    if (!response.ok) {
      throw new Error(`Failed to resolve approval: ${response.statusText}`);
    }
  },
};

export default approvalService;
