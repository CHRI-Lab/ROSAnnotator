import { DataViewContent } from "./DataViewContent";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import { SxProps, Theme } from "@mui/material/styles";

import { DataViewDefinition, ViewPanelContext } from "./viewRegistry";

type ViewPanelProps = {
  view: DataViewDefinition;
  context: ViewPanelContext;
  sx?: SxProps<Theme>;
};

const ViewPanel = ({ view, context, sx }: ViewPanelProps) => {

  return (
    <Box
      minWidth={0}
      minHeight={0}
      display="flex"
      flexDirection="column"
      overflow="hidden"
      margin={1}
      sx={sx}
    >
      <Box sx={{ borderBottom: 1, borderColor: "divider", px: 1, py: 0.75 }}>
        <Typography color="primary">{view.label}</Typography>
      </Box>
      <Box key={view.id} flex={1} minHeight={0} overflow={view.id === 'video' ? 'hidden' : 'auto'}>
        <DataViewContent view={view} context={context} />
      </Box>
    </Box>
  );
};

export default ViewPanel;
