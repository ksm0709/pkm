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
  commandShortcut: string;
  href: (vaultName: string) => string;
};

export const appNavPages: AppNavPage[] = [
  {
    id: "notes",
    label: "Notes",
    meta: "index",
    commandLabel: "Open notes",
    commandHint: "index",
    commandShortcut: "n",
    href: (vaultName) => `/${vaultName}`,
  },
  {
    id: "tags",
    label: "Tags",
    meta: "index",
    commandLabel: "Open tags",
    commandHint: "tag index",
    commandShortcut: "t",
    href: (vaultName) => `/${vaultName}/tags`,
  },
  {
    id: "graph",
    label: "Graph",
    meta: "network",
    commandLabel: "Open graph",
    commandHint: "network",
    commandShortcut: "g",
    href: (vaultName) => `/${vaultName}/graph`,
  },
  {
    id: "ask",
    label: "Ask",
    meta: "agent",
    commandLabel: "Open ask",
    commandHint: "agent",
    commandShortcut: "a",
    href: (vaultName) => `/${vaultName}/ask`,
  },
  {
    id: "logger",
    label: "Logger",
    meta: "daily log",
    commandLabel: "Open logger",
    commandHint: "daily log",
    commandShortcut: "l",
    href: (vaultName) => `/${vaultName}/logger`,
  },
  {
    id: "workflows",
    label: "Workflows",
    meta: "automation",
    commandLabel: "Open workflows",
    commandHint: "automation",
    commandShortcut: "w",
    href: (vaultName) => `/${vaultName}/workflows`,
  },
  {
    id: "daily",
    label: "Daily",
    meta: "ledger",
    commandLabel: "Open daily",
    commandHint: "ledger",
    commandShortcut: "d",
    href: (vaultName) => `/${vaultName}/daily`,
  },
  {
    id: "configs",
    label: "Configs",
    meta: "settings",
    commandLabel: "Open configs",
    commandHint: "settings",
    commandShortcut: "c",
    href: (vaultName) => `/${vaultName}/configs`,
  },
];
