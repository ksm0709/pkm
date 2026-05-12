export type AppNavPageId =
  | "notes"
  | "tags"
  | "graph"
  | "ask"
  | "logger"
  | "workflows"
  | "daily"
  | "configs";

export type AppNavPage = {
  id: AppNavPageId;
  label: string;
  meta: string;
  commandLabel: string;
  commandHint: string;
  href: (vaultName: string) => string;
};

export const appNavPages: AppNavPage[] = [
  {
    id: "notes",
    label: "Notes",
    meta: "index",
    commandLabel: "Open notes",
    commandHint: "index",
    href: (vaultName) => `/${vaultName}`,
  },
  {
    id: "tags",
    label: "Tags",
    meta: "index",
    commandLabel: "Open tags",
    commandHint: "tag index",
    href: (vaultName) => `/${vaultName}/tags`,
  },
  {
    id: "graph",
    label: "Graph",
    meta: "network",
    commandLabel: "Open graph",
    commandHint: "network",
    href: (vaultName) => `/${vaultName}/graph`,
  },
  {
    id: "ask",
    label: "Ask",
    meta: "agent",
    commandLabel: "Open ask",
    commandHint: "agent",
    href: (vaultName) => `/${vaultName}/ask`,
  },
  {
    id: "logger",
    label: "Logger",
    meta: "daily log",
    commandLabel: "Open logger",
    commandHint: "daily log",
    href: (vaultName) => `/${vaultName}/logger`,
  },
  {
    id: "workflows",
    label: "Workflows",
    meta: "automation",
    commandLabel: "Open workflows",
    commandHint: "automation",
    href: (vaultName) => `/${vaultName}/workflows`,
  },
  {
    id: "daily",
    label: "Daily",
    meta: "ledger",
    commandLabel: "Open daily",
    commandHint: "ledger",
    href: (vaultName) => `/${vaultName}/daily`,
  },
  {
    id: "configs",
    label: "Configs",
    meta: "settings",
    commandLabel: "Open configs",
    commandHint: "settings",
    href: (vaultName) => `/${vaultName}/configs`,
  },
];
