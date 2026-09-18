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

const cloneAxes = (axes: TimelineAxis[]) =>
  JSON.parse(JSON.stringify(axes)) as TimelineAxis[];

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
) => {
  const nextAxes = cloneAxes(currentAxes);
  instruction.steps.forEach((step) => {
    const parameters = step.parameters ?? {};
    const axisId = Number(parameters.axisId);

    if (step.action === "addAxi") {
      if (!Number.isFinite(axisId) || nextAxes.some((axis) => axis.id === axisId)) {
        return;
      }
      nextAxes.push({
        id: axisId,
        type: "Type-in",
        axisName: String(parameters.axisName || `Axis ${axisId}`),
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
        !Number.isFinite(block.start) ||
        !Number.isFinite(block.end) ||
        block.end < block.start
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
