import { AIInstruction } from "../../types/aiRecords";

type TimelineBlock = {
  start: number;
  end: number;
  text?: string;
};

type TimelineAxis = {
  id: number;
  type: string;
  axisName?: string;
  typeName?: string;
  shortcutKey?: string;
  blocks: TimelineBlock[];
};

export type TimelineScope = {
  axisIds: number[];
  allowNew: boolean;
};

const stepAxisId = (step: AIInstruction["steps"][number]) =>
  Number(step.parameters?.axisId);

export const instructionExceedsTimelineScope = (
  instruction: AIInstruction,
  scope: TimelineScope,
) => {
  const selectedIds = new Set(scope.axisIds);
  const proposedNewIds = new Set(
    instruction.steps
      .filter((step) => step.action === "addAxi")
      .map(stepAxisId)
      .filter(Number.isFinite),
  );
  return instruction.steps.some((step) => {
    const axisId = stepAxisId(step);
    if (!Number.isFinite(axisId)) return true;
    if (step.action === "addAxi") return !scope.allowNew;
    return !selectedIds.has(axisId) && !(scope.allowNew && proposedNewIds.has(axisId));
  });
};

export const filterInstructionToTimelineScope = (
  instruction: AIInstruction,
  scope: TimelineScope,
): AIInstruction => {
  const selectedIds = new Set(scope.axisIds);
  const permittedNewIds = new Set(
    scope.allowNew
      ? instruction.steps
          .filter((step) => step.action === "addAxi")
          .map(stepAxisId)
          .filter(Number.isFinite)
      : [],
  );
  return {
    ...instruction,
    steps: instruction.steps.filter((step) => {
      const axisId = stepAxisId(step);
      if (!Number.isFinite(axisId)) return false;
      if (step.action === "addAxi") return permittedNewIds.has(axisId);
      return selectedIds.has(axisId) || permittedNewIds.has(axisId);
    }),
  };
};

const cloneAxes = (axes: TimelineAxis[]) =>
  JSON.parse(JSON.stringify(axes)) as TimelineAxis[];

const normalizedAxisName = (name: string) => name.trim().toLocaleLowerCase();

export const isDuplicateAxisName = (
  axes: Array<{ id: number; axisName?: string }>,
  axisId: number,
  proposedName: string,
) => {
  const normalizedName = normalizedAxisName(proposedName);
  return Boolean(normalizedName) && axes.some(
    (axis) =>
      axis.id !== axisId &&
      normalizedAxisName(axis.axisName || "") === normalizedName,
  );
};

const nextUniqueAxisName = (baseName: string, usedNames: Set<string>) => {
  let suffix = 1;
  let candidate = `${baseName} ${suffix}`;
  while (usedNames.has(normalizedAxisName(candidate))) {
    suffix += 1;
    candidate = `${baseName} ${suffix}`;
  }
  return candidate;
};

export const requiresAIChangeConfirmation = (
  instruction: AIInstruction,
  currentAxes: Array<{ id: number }>,
) => {
  const existingAxisIds = new Set(currentAxes.map((axis) => axis.id));
  const newAxisIds = new Set(
    instruction.steps
      .filter((step) => step.action === "addAxi")
      .map((step) => Number(step.parameters?.axisId)),
  );

  return instruction.steps.some((step) => {
    const action = step.action.toLowerCase();
    return (
      action === "deleteaxi" ||
      action === "deleteblock" ||
      (action === "addblock" &&
        existingAxisIds.has(Number(step.parameters?.axisId)) &&
        !newAxisIds.has(Number(step.parameters?.axisId))) ||
      action.startsWith("update") ||
      action.startsWith("edit") ||
      action.startsWith("modify")
    );
  });
};

export const applyAIInstruction = (
  currentAxes: TimelineAxis[],
  instruction: AIInstruction,
  duration: number,
) => {
  const nextAxes = cloneAxes(currentAxes);
  const usedAxisNames = new Set(
    nextAxes
      .map((axis) => normalizedAxisName(axis.axisName || ""))
      .filter(Boolean),
  );
  const proposedNameCounts = instruction.steps.reduce((counts, step) => {
    if (step.action !== "addAxi") return counts;
    const baseName = String(step.parameters?.axisName || "").trim();
    if (!baseName) return counts;
    const normalizedName = normalizedAxisName(baseName);
    counts.set(normalizedName, (counts.get(normalizedName) || 0) + 1);
    return counts;
  }, new Map<string, number>());
  instruction.steps.forEach((step) => {
    const parameters = step.parameters ?? {};
    const axisId = Number(parameters.axisId);

    if (step.action === "addAxi") {
      if (!Number.isFinite(axisId) || nextAxes.some((axis) => axis.id === axisId)) {
        return;
      }
      const baseName = String(parameters.axisName || `Axis ${axisId}`).trim();
      const normalizedName = normalizedAxisName(baseName);
      const needsSuffix =
        usedAxisNames.has(normalizedName) ||
        (proposedNameCounts.get(normalizedName) || 0) > 1;
      const axisName = needsSuffix
        ? nextUniqueAxisName(baseName, usedAxisNames)
        : baseName;
      usedAxisNames.add(normalizedAxisName(axisName));
      nextAxes.push({
        id: axisId,
        type: "Type-in",
        axisName,
        blocks: [],
        typeName: "",
        shortcutKey: "",
      });
      return;
    }

    const axisIndex = nextAxes.findIndex((axis) => axis.id === axisId);
    if (step.action === "addBlock") {
      if (axisIndex === -1) {
        return;
      }
      const block = {
        start: Number(parameters.start),
        end: Number(parameters.end),
        text: String(parameters.text ?? ""),
      };
      if (
        !Number.isFinite(duration) ||
        duration < 0 ||
        !Number.isFinite(block.start) ||
        !Number.isFinite(block.end) ||
        block.start < 0 ||
        block.end < block.start ||
        block.end > duration
      ) {
        return;
      }
      const overlaps = nextAxes[axisIndex].blocks.some(
        (existingBlock) =>
          block.start <= existingBlock.end && block.end >= existingBlock.start,
      );
      if (overlaps) {
        return;
      }
      nextAxes[axisIndex].blocks.push(block);
      return;
    }

    if (step.action === "deleteBlock") {
      const blockIndex = Number(parameters.blockIndex);
      if (
        axisIndex === -1 ||
        !Number.isInteger(blockIndex) ||
        blockIndex < 0 ||
        blockIndex >= nextAxes[axisIndex].blocks.length
      ) {
        return;
      }
      nextAxes[axisIndex].blocks.splice(blockIndex, 1);
      return;
    }

    if (step.action === "deleteAxi") {
      if (axisIndex === -1) {
        return;
      }
      nextAxes.splice(axisIndex, 1);
    }
  });

  return nextAxes;
};
