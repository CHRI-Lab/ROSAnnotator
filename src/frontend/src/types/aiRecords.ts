export type AIInstructionStep = {
  action: string;
  parameters?: Record<string, unknown>;
};

export type AIInstruction = {
  type: "instruction";
  steps: AIInstructionStep[];
};

export type AIRecord = {
  schema_version: number;
  run_id: string;
  timestamp: string;
  model_selection: {
    requested: string;
    used: string;
    context_routes: Record<string, unknown>;
  };
  model: Record<string, unknown>;
  parameters: Record<string, unknown>;
  prompts: {
    system?: string;
    user?: string;
  };
  ai_response: string;
  [key: string]: unknown;
};

export type AssistantRequestOptions = {
  fallbackConsent?: {
    from: "local" | "remote";
    to: "local" | "remote";
    userConsented: true;
  };
};
