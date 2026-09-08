import { ReactNode, useState } from "react";
import Box from "@mui/material/Box";
import Tab from "@mui/material/Tab";
import Tabs from "@mui/material/Tabs";

type RightAssistantPanelProps = {
  codebook: ReactNode;
  assistant: ReactNode;
};

const RightAssistantPanel = ({
  codebook,
  assistant,
}: RightAssistantPanelProps) => {
  const [selectedTab, setSelectedTab] = useState(1);

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
      <Tabs
        value={selectedTab}
        onChange={(_event, value) => setSelectedTab(value)}
        aria-label="Codebook and AI Assistant"
      >
        <Tab label="Codebook" />
        <Tab label="AI Assistant" />
      </Tabs>
      <Box flex={1} minHeight={0} overflow="auto">
        {selectedTab === 0 ? codebook : assistant}
      </Box>
    </Box>
  );
};

export default RightAssistantPanel;
