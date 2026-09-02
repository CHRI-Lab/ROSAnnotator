export type AssistantMode = "remote" | "local" | "hybrid";
export type AssistantTarget = "remote" | "local";

export type AssistantContextRoutes = {
  transcript: AssistantTarget;
  frames: AssistantTarget;
  codebook: AssistantTarget;
  timeline: AssistantTarget;
};

export type AssistantRouting = {
  mode: AssistantMode;
  contextRoutes: AssistantContextRoutes;
};

export type AssistantReply = {
  text: string;
  assistantMode: AssistantMode;
  isError?: boolean;
  canFallbackToRemote?: boolean;
};

export const ASSISTANT_CONTEXTS: Array<{
  key: keyof AssistantContextRoutes;
  label: string;
}> = [
  { key: "transcript", label: "Transcript" },
  { key: "frames", label: "Video frames" },
  { key: "codebook", label: "Codebook" },
  { key: "timeline", label: "Timeline" },
];

export const DEFAULT_ASSISTANT_ROUTING: AssistantRouting = {
  mode: "remote",
  contextRoutes: {
    transcript: "remote",
    frames: "remote",
    codebook: "remote",
    timeline: "remote",
  },
};

export const isAssistantRouting = (value: unknown): value is AssistantRouting => {
  if (!value || typeof value !== "object") {
    return false;
  }

  const candidate = value as Partial<AssistantRouting>;
  if (!candidate.mode || !["remote", "local", "hybrid"].includes(candidate.mode)) {
    return false;
  }

  const routes = candidate.contextRoutes;
  if (!routes) {
    return false;
  }

  return ASSISTANT_CONTEXTS.every(({ key }) =>
    ["remote", "local"].includes(routes[key]),
  );
};
