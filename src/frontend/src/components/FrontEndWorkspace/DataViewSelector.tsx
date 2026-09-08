import Box from "@mui/material/Box";
import MenuItem from "@mui/material/MenuItem";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";

import { DataViewDefinition } from "./viewRegistry";

type DataViewSelectorProps = {
  panelCount: number;
  selections: string[];
  views: DataViewDefinition[];
  onPanelCountChange: (count: number) => void;
  onSelectionChange: (panelIndex: number, viewId: string) => void;
};

const DataViewSelector = ({
  panelCount,
  selections,
  views,
  onPanelCountChange,
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

    {selections.slice(0, panelCount).map((selection, panelIndex) => (
      <TextField
        key={panelIndex}
        select
        fullWidth
        size="small"
        label={`Panel ${panelIndex + 1}`}
        value={selection}
        onChange={(event) =>
          onSelectionChange(panelIndex, event.target.value)
        }
        sx={{ marginBottom: 1.5 }}
      >
        {views.map((view) => (
          <MenuItem key={view.id} value={view.id}>
            {view.label}
          </MenuItem>
        ))}
      </TextField>
    ))}
  </Box>
);

export default DataViewSelector;
