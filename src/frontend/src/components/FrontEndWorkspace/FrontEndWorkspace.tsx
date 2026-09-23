import { useState } from "react";
import Box from "@mui/material/Box";

import DataViewSelector from "./DataViewSelector";
import ViewPanel from "./ViewPanel";
import {
  availableViews,
  viewsWithAvailability,
  DataViewDefinition,
  ViewPanelContext,
} from "./viewRegistry";

type FrontEndWorkspaceProps = {
  context: ViewPanelContext;
};

const initialSelections = [
  "video",
  "annotations",
  "transcript",
  "statistics-annotations",
];

const getGridLayout = (panelCount: number) => {
  if (panelCount === 1) {
    return { columns: "minmax(0, 1fr)", rows: "minmax(0, 1fr)" };
  }
  if (panelCount === 2) {
    return {
      columns: "repeat(2, minmax(0, 1fr))",
      rows: "minmax(0, 1fr)",
    };
  }
  if (panelCount === 3) {
    return {
      columns: "repeat(2, minmax(0, 1fr))",
      rows: "repeat(2, minmax(0, 1fr))",
    };
  }
  return {
    columns: "repeat(2, minmax(0, 1fr))",
    rows: "repeat(2, minmax(0, 1fr))",
  };
};

const getPanelPlacement = (
  panelCount: number,
  panelIndex: number,
  largeSide: "left" | "right",
) => {
  if (panelCount !== 3) {
    return undefined;
  }

  if (largeSide === "left") {
    return panelIndex === 0
      ? { gridColumn: 1, gridRow: "1 / span 2" }
      : { gridColumn: 2, gridRow: panelIndex };
  }

  return panelIndex === 2
    ? { gridColumn: 2, gridRow: "1 / span 2" }
    : { gridColumn: 1, gridRow: panelIndex + 1 };
};

const findView = (viewId: string): DataViewDefinition =>
  availableViews.find((view) => view.id === viewId) ?? availableViews[0];

const FrontEndWorkspace = ({ context }: FrontEndWorkspaceProps) => {
  const [panelCount, setPanelCount] = useState(2);
  const [threePanelLargeSide, setThreePanelLargeSide] = useState<
    "left" | "right"
  >("left");
  const [selections, setSelections] = useState(initialSelections);
  const layout = getGridLayout(panelCount);
  const views = viewsWithAvailability(context.views);
  const effectiveSelections = selections.map(selection =>
    selection === 'video' && context.views?.video?.status !== 'loading' &&
    context.views?.video?.available === false
      ? ['audio', 'wrench'].find(id => context.views?.[id]?.available) || selection : selection);

  const handleSelectionChange = (panelIndex: number, viewId: string) => {
    setSelections((currentSelections) =>
      currentSelections.map((selection, index) =>
        index === panelIndex ? viewId : selection,
      ),
    );
  };

  return (
    <Box display="flex" width="100%" flex={1} minHeight={0} overflow="hidden">
      <DataViewSelector
        panelCount={panelCount}
        threePanelLargeSide={threePanelLargeSide}
        selections={effectiveSelections}
        views={views}
        onPanelCountChange={setPanelCount}
        onThreePanelLargeSideChange={setThreePanelLargeSide}
        onSelectionChange={handleSelectionChange}
      />
      <Box
        display="grid"
        gridTemplateColumns={layout.columns}
        gridTemplateRows={layout.rows}
        flex={1}
        minWidth={0}
        minHeight={0}
        overflow="hidden"
      >
        {effectiveSelections.slice(0, panelCount).map((selection, panelIndex) => (
          <ViewPanel
            key={panelIndex}
            view={findView(selection)}
            context={context}
            sx={getPanelPlacement(
              panelCount,
              panelIndex,
              threePanelLargeSide,
            )}
          />
        ))}
      </Box>
    </Box>
  );
};

export default FrontEndWorkspace;
