import Box from "@mui/material/Box";
import IconButton from "@mui/material/IconButton";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import SaveOutlinedIcon from "@mui/icons-material/SaveOutlined";
import SettingsOutlinedIcon from "@mui/icons-material/SettingsOutlined";

type AppHeaderProps = {
  rosBagFileName: string;
  disabled: boolean;
  onSave: () => void;
};

const AppHeader = ({
  rosBagFileName,
  disabled,
  onSave,
}: AppHeaderProps) => (
  <Box
    component="header"
    height={64}
    flexShrink={0}
    display="flex"
    alignItems="center"
    paddingX={2}
    gap={1.5}
    bgcolor="background.paper"
    borderBottom={1}
    borderColor="divider"
  >
    <Box
      component="img"
      src="/rosannotator-logo.png"
      alt="ROSAnnotator"
      width={44}
      height={44}
      sx={{ objectFit: "contain", flexShrink: 0 }}
    />
    <Typography
      variant="body1"
      noWrap
      title={rosBagFileName}
      sx={{ minWidth: 0 }}
    >
      {rosBagFileName}
    </Typography>

    <Box flex={1} />

    <Tooltip title={disabled ? "Waiting for data to finish loading" : "Save annotation"}>
      <span>
        <IconButton
          aria-label="Save annotation"
          onClick={onSave}
          disabled={disabled}
          color="inherit"
        >
          <SaveOutlinedIcon />
        </IconButton>
      </span>
    </Tooltip>
    <Tooltip title="Settings (coming soon)">
      <span>
        <IconButton aria-label="Settings (coming soon)" disabled>
          <SettingsOutlinedIcon />
        </IconButton>
      </span>
    </Tooltip>
  </Box>
);

export default AppHeader;
