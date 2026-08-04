export type CmdKCoreCommandId =
  | "cmd:jump"
  | "cmd:daily"
  | "cmd:add-note"
  | "cmd:daily-subnote"
  | "cmd:index-vault"
  | "cmd:switch"
  | "cmd:theme";

export type CmdKCommandShortcut = {
  id: CmdKCoreCommandId;
  label: string;
  hint: string;
  shortcut: string;
};

export const cmdkCoreCommandShortcuts: CmdKCommandShortcut[] = [
  {
    id: "cmd:jump",
    label: "Jump to note…",
    hint: "search",
    shortcut: "/",
  },
  {
    id: "cmd:daily",
    label: "Open today's daily note",
    hint: "daily",
    shortcut: "y",
  },
  {
    id: "cmd:add-note",
    label: "Add note",
    hint: "note",
    shortcut: "a",
  },
  {
    id: "cmd:daily-subnote",
    label: "Add daily sub-note",
    hint: "daily subnote",
    shortcut: "s",
  },
  {
    id: "cmd:index-vault",
    label: "Index vault",
    hint: "rebuild search and graph",
    shortcut: "i",
  },

  {
    id: "cmd:switch",
    label: "Switch vault…",
    hint: "switch",
    shortcut: "v",
  },
  {
    id: "cmd:theme",
    label: "Toggle theme",
    hint: "theme",
    shortcut: "h",
  },
];
