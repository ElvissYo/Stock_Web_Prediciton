const icon = (body) =>
  `<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">${body}</svg>`;

export const TOOL_GROUPS = [
  [
    {
      id: "select",
      label: "Select",
      shortcut: "V",
      icon: icon('<path d="M6 3l10 9-5 1.1 3.5 6.1-2.2 1.2-3.4-6-3.1 3z" />'),
    },
    {
      id: "crosshair",
      label: "Crosshair",
      shortcut: "",
      icon: icon('<path d="M12 3v18M3 12h18" /><circle cx="12" cy="12" r="2" />'),
    },
  ],
  [
    {
      id: "trendline",
      label: "Trend Line",
      shortcut: "T",
      icon: icon('<path d="M4 17L20 7" /><circle cx="4" cy="17" r="2" /><circle cx="20" cy="7" r="2" />'),
    },
    {
      id: "horizontal",
      label: "Horizontal Line",
      shortcut: "H",
      icon: icon('<path d="M4 12h16" /><path d="M7 9v6M17 9v6" />'),
    },
    {
      id: "vertical",
      label: "Vertical Line",
      shortcut: "",
      icon: icon('<path d="M12 4v16" /><path d="M9 7h6M9 17h6" />'),
    },
    {
      id: "ray",
      label: "Ray Line",
      shortcut: "",
      icon: icon('<path d="M4 17L17 8" /><path d="M15 5l5 1-2 5" />'),
    },
    {
      id: "channel",
      label: "Parallel Channel",
      shortcut: "",
      icon: icon('<path d="M5 16L17 8M8 20L20 12" /><path d="M6 12l4 6M14 6l4 6" />'),
    },
  ],
  [
    {
      id: "fibonacci",
      label: "Fibonacci Retracement",
      shortcut: "F",
      icon: icon('<path d="M5 5h14M5 9h14M5 13h14M5 17h14" /><path d="M8 5v12" />'),
    },
    {
      id: "rectangle",
      label: "Rectangle",
      shortcut: "R",
      icon: icon('<rect x="5" y="6" width="14" height="12" rx="1" />'),
    },
    {
      id: "brush",
      label: "Brush",
      shortcut: "",
      icon: icon('<path d="M5 16c4-8 7 4 14-5" /><path d="M4 20c2-1 4-1 6 0" />'),
    },
    {
      id: "text",
      label: "Text",
      shortcut: "",
      icon: icon('<path d="M6 6h12M12 6v13" /><path d="M9 19h6" />'),
    },
    {
      id: "arrow",
      label: "Arrow Marker",
      shortcut: "",
      icon: icon('<path d="M5 18L18 5" /><path d="M12 5h6v6" />'),
    },
    {
      id: "measure",
      label: "Measure",
      shortcut: "",
      icon: icon('<path d="M5 17L19 7" /><path d="M7 14l3 3M14 7l3 3" />'),
    },
    {
      id: "zoom",
      label: "Zoom Area",
      shortcut: "",
      icon: icon('<circle cx="10" cy="10" r="5" /><path d="M14 14l5 5" /><path d="M8 10h4M10 8v4" />'),
    },
  ],
  [
    {
      id: "magnet",
      label: "Magnet Mode",
      toggle: true,
      icon: icon('<path d="M7 4v7a5 5 0 0010 0V4" /><path d="M7 8h4M13 8h4M7 4h4M13 4h4" />'),
    },
    {
      id: "lock",
      label: "Lock Drawings",
      toggle: true,
      icon: icon('<rect x="6" y="10" width="12" height="10" rx="2" /><path d="M9 10V7a3 3 0 016 0v3" />'),
    },
    {
      id: "hide",
      label: "Hide/Show Drawings",
      toggle: true,
      icon: icon('<path d="M3 12s3-6 9-6 9 6 9 6-3 6-9 6-9-6-9-6z" /><circle cx="12" cy="12" r="3" />'),
    },
    {
      id: "delete",
      label: "Delete Selected",
      shortcut: "Delete",
      icon: icon('<path d="M5 7h14M10 11v6M14 11v6M8 7l1-3h6l1 3M7 7l1 13h8l1-13" />'),
    },
  ],
];

export const TOOLS = TOOL_GROUPS.flat();

export function findTool(toolId) {
  return TOOLS.find((tool) => tool.id === toolId);
}
