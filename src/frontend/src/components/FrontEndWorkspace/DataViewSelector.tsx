import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import MenuItem from "@mui/material/MenuItem";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import Tooltip from "@mui/material/Tooltip";

import { DataViewDefinition } from "./viewRegistry";

type DataViewSelectorProps = {
  panelCount: number;
  threePanelLargeSide: "left" | "right";
  selections: string[];
  views: DataViewDefinition[];
  onPanelCountChange: (count: number) => void;
  onThreePanelLargeSideChange: (side: "left" | "right") => void;
  onSelectionChange: (panelIndex: number, viewId: string) => void;
};

const ThreePanelLayoutPreview = ({ side }: { side: "left" | "right" }) => (
  <Box
    width={42}
    height={30}
    display="grid"
    gridTemplateColumns="repeat(2, 1fr)"
    gridTemplateRows="repeat(2, 1fr)"
    gap="2px"
    aria-hidden="true"
  >
    <Box
      border={1}
      gridColumn={side === "left" ? 1 : 2}
      gridRow="1 / span 2"
    />
    <Box border={1} gridColumn={side === "left" ? 2 : 1} gridRow={1} />
    <Box border={1} gridColumn={side === "left" ? 2 : 1} gridRow={2} />
  </Box>
);

const DataViewSelector = ({
  panelCount,
  threePanelLargeSide,
  selections,
  views,
  onPanelCountChange,
  onThreePanelLargeSideChange,
  onSelectionChange,
}: DataViewSelectorProps) => (
  <Box
    width={190}
    minWidth={190}
    height="100%"
    boxSizing="border-box"
    borderRight={1}
    borderColor="divider"
    bgcolor="background.paper"
    padding={1.5}
    overflow="auto"
  >
    <Typography variant="subtitle2" marginBottom={1}>
      View Panels
    </Typography>
    <TextField
      select
      fullWidth
      size="small"
      label="Visible panels"
      value={panelCount}
      onChange={(event) => onPanelCountChange(Number(event.target.value))}
      sx={{ marginBottom: 2 }}
    >
      {[1, 2, 3, 4].map((count) => (
        <MenuItem key={count} value={count}>
          {count}
        </MenuItem>
      ))}
    </TextField>

    {panelCount === 3 && (
      <Box marginBottom={2}>
        <Typography variant="caption" display="block" marginBottom={0.75}>
          Layout
        </Typography>
        <Box display="flex" gap={1}>
          {(["left", "right"] as const).map((side) => (
            <Button
              key={side}
              size="small"
              variant={threePanelLargeSide === side ? "contained" : "outlined"}
              aria-label={`Large panel on the ${side}`}
              aria-pressed={threePanelLargeSide === side}
              onClick={() => onThreePanelLargeSideChange(side)}
              sx={{ flex: 1, minWidth: 0, paddingY: 1 }}
            >
              <ThreePanelLayoutPreview side={side} />
            </Button>
          ))}
        </Box>
      </Box>
    )}

    {selections.slice(0, panelCount).map((selection, panelIndex) => (
      <TextField
        key={panelIndex}
        select
        fullWidth
        size="small"
        label={`Panel ${panelIndex + 1}`}
        value={selection}
        onChange={(event) => {
          const target = views.find(view => view.id === event.target.value);
          if (target?.available === false && target.status !== 'loading') return;
          onSelectionChange(panelIndex, event.target.value);
        }}
        sx={{ marginBottom: 1.5 }}
      >
        {views.map((view) => (
          <MenuItem key={view.id} value={view.id} disabled={view.available === false && view.status !== "loading"}
            sx={{ '&.Mui-disabled': { pointerEvents: 'auto' } }}>
            <Tooltip describeChild title={view.available === false && view.status !== 'loading'
              ? 'Data type not available' : ''}>
              <span style={{ display: 'block', width: '100%' }}>{view.label}</span>
            </Tooltip>
          </MenuItem>
        ))}
      </TextField>
    ))}
    {views.filter(view => view.available === false && view.status !== 'loading').map(view => (
      <Box key={view.id} role="status" sx={{ mt: 1.5, overflowWrap: 'anywhere' }}>
        <Typography variant="caption" component="div" fontWeight="bold">
          {view.label} unavailable
        </Typography>
        <Typography variant="caption" component="div" color="text.secondary">
          {view.reason || 'No usable data is available for this view.'}
        </Typography>
      </Box>
    ))}
  </Box>
);

export default DataViewSelector;
