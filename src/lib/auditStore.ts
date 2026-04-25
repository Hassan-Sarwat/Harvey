import { create } from "zustand";
import { persist } from "zustand/middleware";

export type Violation = {
  severity: "High" | "Medium";
  clause: string;
  issue: string;
  reference: string;
  suggestion: string;
};

export type AuditResult = {
  contract_summary: string;
  contract_value_eur?: number;
  status: "Approved" | "Escalated" | "Rejected";
  escalation_required: boolean;
  violations: Violation[];
};

export type AuditRecord = {
  id: string;
  fileName: string;
  contractText: string;
  result: AuditResult;
  createdAt: number;
};

type Store = {
  audits: AuditRecord[];
  add: (rec: Omit<AuditRecord, "id" | "createdAt">) => AuditRecord;
  clear: () => void;
};

export const useAuditStore = create<Store>()(
  persist(
    (set, get) => ({
      audits: [],
      add: (rec) => {
        const record: AuditRecord = {
          ...rec,
          id: crypto.randomUUID(),
          createdAt: Date.now(),
        };
        set({ audits: [record, ...get().audits].slice(0, 50) });
        return record;
      },
      clear: () => set({ audits: [] }),
    }),
    { name: "bmw-audit-history" },
  ),
);