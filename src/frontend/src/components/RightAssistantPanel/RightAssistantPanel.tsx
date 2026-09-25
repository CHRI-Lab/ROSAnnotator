import { ReactNode, useState } from "react";
import Box from "@mui/material/Box";
import Tab from "@mui/material/Tab";
import Tabs from "@mui/material/Tabs";
import IconButton from "@mui/material/IconButton";
import Tooltip from "@mui/material/Tooltip";
import DeleteOutlineIcon from "@mui/icons-material/DeleteOutline";
import Dialog from "@mui/material/Dialog";
import DialogTitle from "@mui/material/DialogTitle";
import DialogContent from "@mui/material/DialogContent";
import DialogContentText from "@mui/material/DialogContentText";
import DialogActions from "@mui/material/DialogActions";
import Button from "@mui/material/Button";

type RightAssistantPanelProps = {
  codebook: ReactNode;
  assistant: ReactNode;
  onClearConversation: () => Promise<void>;
};

const RightAssistantPanel = ({
  codebook,
  assistant,
  onClearConversation,
}: RightAssistantPanelProps) => {
  const [selectedTab, setSelectedTab] = useState(1);
  const [confirmClear, setConfirmClear] = useState(false);
  const [clearing, setClearing] = useState(false);
  const [clearError, setClearError] = useState("");

  const clearConversation = async () => {
    setClearing(true);
    setClearError("");
    try {
      await onClearConversation();
      setConfirmClear(false);
    } catch {
      setClearError("Could not clear conversation history. Please try again.");
    } finally {
      setClearing(false);
    }
  };

  return (
    <Box
      flex={0.3}
      height="100%"
      bgcolor="background.paper"
      borderLeft={1}
      borderColor="divider"
      display="flex"
      flexDirection="column"
      overflow="hidden"
    >
      <Box display="flex" alignItems="center">
        <Tabs
          value={selectedTab}
          onChange={(_event, value) => setSelectedTab(value)}
          aria-label="Codebook and AI Assistant"
          sx={{ flex: 1, minWidth: 0 }}
        >
          <Tab label="Codebook" />
          <Tab label="AI Assistant" />
        </Tabs>
        {selectedTab === 1 && (
          <Tooltip title="Clear conversation history">
            <IconButton
              aria-label="Clear conversation history"
              onClick={() => setConfirmClear(true)}
              sx={{ mr: 1 }}
            >
              <DeleteOutlineIcon />
            </IconButton>
          </Tooltip>
        )}
      </Box>
      <Dialog open={confirmClear} onClose={() => !clearing && setConfirmClear(false)}>
        <DialogTitle>Clear conversation history?</DialogTitle>
        <DialogContent>
          <DialogContentText>
            This action will clear your conversation history with AI assistant in the chatbox and also backend history (not the saved AI records).
          </DialogContentText>
          {clearError && <DialogContentText color="error">{clearError}</DialogContentText>}
        </DialogContent>
        <DialogActions>
          <Button disabled={clearing} onClick={() => setConfirmClear(false)}>Cancel</Button>
          <Button disabled={clearing} onClick={clearConversation} color="error" variant="contained">
            Clear
          </Button>
        </DialogActions>
      </Dialog>
      <Box flex={1} minHeight={0} overflow="auto">
        <Box
          display={selectedTab === 0 ? "block" : "none"}
          height="100%"
          role="tabpanel"
          aria-hidden={selectedTab !== 0}
        >
          {codebook}
        </Box>
        <Box
          display={selectedTab === 1 ? "block" : "none"}
          height="100%"
          role="tabpanel"
          aria-hidden={selectedTab !== 1}
        >
          {assistant}
        </Box>
      </Box>
    </Box>
  );
};

export default RightAssistantPanel;
