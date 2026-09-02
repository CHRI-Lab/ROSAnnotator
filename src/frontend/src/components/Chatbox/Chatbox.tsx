import { useEffect, useState } from "react";
import Box from "@mui/material/Box";
import TextField from "@mui/material/TextField";
import Button from "@mui/material/Button";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogContentText from "@mui/material/DialogContentText";
import DialogTitle from "@mui/material/DialogTitle";
import MenuItem from "@mui/material/MenuItem";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import {
  ASSISTANT_CONTEXTS,
  AssistantMode,
  AssistantReply,
  AssistantRouting,
  AssistantTarget,
  DEFAULT_ASSISTANT_ROUTING,
  isAssistantRouting,
} from "../../types/assistantRouting";

type ChatMessage = {
  sender: "user" | "gpt";
  text: string;
  assistantMode?: AssistantMode;
  isError?: boolean;
};

type ChatboxProps = {
  onSendMessage: (
    message: string,
    assistantRouting: AssistantRouting,
  ) => Promise<AssistantReply>;
};

type PendingRemoteFallback = {
  message: string;
};

const ASSISTANT_ROUTING_STORAGE_KEY = "rosannotator-assistant-routing";

const loadAssistantRouting = (): AssistantRouting | null => {
  try {
    const storedRouting = localStorage.getItem(ASSISTANT_ROUTING_STORAGE_KEY);
    if (storedRouting) {
      const parsedRouting: unknown = JSON.parse(storedRouting);
      if (isAssistantRouting(parsedRouting)) {
        return parsedRouting;
      }
    }
  } catch {
    // Ignore unavailable storage or invalid previous values and use the
    // behavior-compatible remote default.
  }

  return null;
};

const upwardMenuProps = {
  anchorOrigin: { vertical: "top", horizontal: "left" } as const,
  transformOrigin: { vertical: "bottom", horizontal: "left" } as const,
};

const formatAssistantMode = (mode: AssistantMode | undefined) => {
  const value = mode ?? "remote";
  return value.charAt(0).toUpperCase() + value.slice(1);
};

const Chatbox = ({ onSendMessage }: ChatboxProps) => {
  const [message, setMessage] = useState("");
  const [chatHistory, setChatHistory] = useState<ChatMessage[]>([]);
  const [initialAssistantRouting] = useState(loadAssistantRouting);
  const [assistantRouting, setAssistantRouting] = useState<AssistantRouting>(
    initialAssistantRouting ?? DEFAULT_ASSISTANT_ROUTING,
  );
  const [hasAssistantSelection, setHasAssistantSelection] = useState(
    initialAssistantRouting !== null,
  );
  const [pendingRemoteFallback, setPendingRemoteFallback] =
    useState<PendingRemoteFallback | null>(null);

  useEffect(() => {
    if (!hasAssistantSelection) {
      return;
    }

    try {
      localStorage.setItem(
        ASSISTANT_ROUTING_STORAGE_KEY,
        JSON.stringify(assistantRouting),
      );
    } catch {
      // The in-memory selection still remains stable when storage is blocked.
    }
  }, [assistantRouting, hasAssistantSelection]);

  const handleModeChange = (mode: AssistantRouting["mode"]) => {
    setHasAssistantSelection(true);
    setAssistantRouting((currentRouting) => ({
      mode,
      contextRoutes:
        mode === "hybrid"
          ? currentRouting.contextRoutes
          : {
              transcript: mode,
              frames: mode,
              codebook: mode,
              timeline: mode,
            },
    }));
  };

  const handleContextRouteChange = (
    context: keyof AssistantRouting["contextRoutes"],
    target: AssistantTarget,
  ) => {
    setAssistantRouting((currentRouting) => ({
      ...currentRouting,
      contextRoutes: {
        ...currentRouting.contextRoutes,
        [context]: target,
      },
    }));
  };

  const handleSendMessage = () => {
    if (message.trim() !== "") {
      const submittedMessage = message;
      const newMessage: ChatMessage = { sender: "user", text: message };
      setChatHistory([...chatHistory, newMessage]);

      onSendMessage(submittedMessage, assistantRouting).then((assistantResponse) => {
        if (assistantResponse.canFallbackToRemote) {
          setPendingRemoteFallback({
            message: submittedMessage,
          });
          return;
        }

        const gptMessage: ChatMessage = {
          sender: "gpt",
          text: assistantResponse.text,
          assistantMode: assistantResponse.assistantMode,
          isError: assistantResponse.isError,
        };
        setChatHistory((prevChatHistory) => [...prevChatHistory, gptMessage]);
      });

      setMessage(""); 
    }
  };

  const handleRemoteFallback = () => {
    if (!pendingRemoteFallback) {
      return;
    }

    const remoteRouting: AssistantRouting = {
      mode: "remote",
      contextRoutes: {
        transcript: "remote",
        frames: "remote",
        codebook: "remote",
        timeline: "remote",
      },
    };
    const fallbackMessage = pendingRemoteFallback.message;

    setPendingRemoteFallback(null);
    setHasAssistantSelection(true);
    setAssistantRouting(remoteRouting);
    onSendMessage(fallbackMessage, remoteRouting).then((assistantResponse) => {
      setChatHistory((history) => [
        ...history,
        {
          sender: "gpt",
          text: assistantResponse.text,
          assistantMode: assistantResponse.assistantMode,
          isError: assistantResponse.isError,
        },
      ]);
    });
  };

  const handleDeclineRemoteFallback = () => {
    if (!pendingRemoteFallback) {
      return;
    }

    setChatHistory((history) => [
      ...history,
      {
        sender: "gpt",
        text: "The local model is unavailable.",
        assistantMode: "local",
        isError: true,
      },
    ]);
    setPendingRemoteFallback(null);
  };

  return (
    <Box
      display="flex"
      flexDirection="column"
      border={1}
      borderColor="gray"
      padding={2}
      overflow="auto"
      height="100%"
    >
      <Dialog
        open={pendingRemoteFallback !== null}
        onClose={handleDeclineRemoteFallback}
      >
        <DialogTitle>Switch to Remote?</DialogTitle>
        <DialogContent>
          <DialogContentText>
            The local language model is not connected. Continuing with Remote
            will send the current transcript, video frames, codebook, and
            timeline context to OpenAI.
          </DialogContentText>
        </DialogContent>
        <DialogActions>
          <Button onClick={handleDeclineRemoteFallback}>Stay Local</Button>
          <Button onClick={handleRemoteFallback} variant="contained" autoFocus>
            Switch to Remote
          </Button>
        </DialogActions>
      </Dialog>
      <Box flexGrow={1} overflow="auto" mb={2}>
        {chatHistory.map((msg, index) => (
          <Box
            key={index}
            mb={1.5}
            display="flex"
            justifyContent={msg.sender === "user" ? "flex-end" : "flex-start"}
          >
            <Box
              sx={{
                maxWidth: "85%",
                px: 1.5,
                py: 1,
                borderRadius: 2,
                bgcolor:
                  msg.sender === "user"
                    ? "primary.main"
                    : msg.isError
                      ? "error.dark"
                      : "action.hover",
                color:
                  msg.sender === "user"
                    ? "primary.contrastText"
                    : msg.isError
                      ? "error.contrastText"
                      : "text.primary",
              }}
            >
            {msg.sender === "gpt" && (
              <Box component="div" sx={{ fontWeight: 700, mb: 0.5 }}>
                {`ROSAnnotator (${formatAssistantMode(msg.assistantMode)})`}
              </Box>
            )}
            {msg.sender === "gpt" ? (
              <Box
                component="div"
                sx={{
                  overflowWrap: "anywhere",
                  "& p": { my: 0.75 },
                  "& p:first-of-type": { mt: 0 },
                  "& p:last-child": { mb: 0 },
                  "& ul, & ol": { my: 0.75, pl: 3 },
                  "& li": { mb: 0.25 },
                  "& pre": {
                    overflowX: "auto",
                    p: 1,
                    borderRadius: 1,
                    bgcolor: "action.hover",
                    color: "text.primary",
                  },
                  "& code": {
                    px: 0.5,
                    borderRadius: 0.5,
                    bgcolor: "action.hover",
                  },
                  "& pre code": { p: 0, bgcolor: "transparent" },
                  "& blockquote": {
                    my: 0.75,
                    ml: 0,
                    pl: 1.5,
                    borderLeft: 3,
                    borderColor: "grey.400",
                    color: "text.secondary",
                  },
                  "& table": {
                    width: "100%",
                    my: 1,
                    borderCollapse: "collapse",
                  },
                  "& th, & td": {
                    p: 0.75,
                    border: 1,
                    borderColor: "divider",
                    textAlign: "left",
                  },
                  "& a": { overflowWrap: "anywhere" },
                }}
              >
                <ReactMarkdown remarkPlugins={[remarkGfm]}>
                  {msg.text}
                </ReactMarkdown>
              </Box>
            ) : (
              <>{msg.text}</>
            )}
            </Box>
          </Box>
        ))}
      </Box>

      <Box mb={1}>
        <TextField
          select
          size="small"
          value={hasAssistantSelection ? assistantRouting.mode : ""}
          onChange={(event) =>
            handleModeChange(event.target.value as AssistantRouting["mode"])
          }
          SelectProps={{
            MenuProps: upwardMenuProps,
            displayEmpty: true,
            renderValue: (selected) => {
              if (!selected) {
                return "AI Assistant";
              }

              return `${selected}`.charAt(0).toUpperCase() + `${selected}`.slice(1);
            },
          }}
          inputProps={{ "aria-label": "AI Assistant" }}
          sx={{ width: 128 }}
        >
          <MenuItem value="remote">Remote</MenuItem>
          <MenuItem value="local">Local</MenuItem>
          <MenuItem value="hybrid">Hybrid</MenuItem>
        </TextField>
      </Box>

      {assistantRouting.mode === "hybrid" && (
        <Box
          display="grid"
          gridTemplateColumns="repeat(2, minmax(0, 1fr))"
          gap={1}
          mb={1}
        >
          {ASSISTANT_CONTEXTS.map(({ key, label }) => (
            <TextField
              key={key}
              select
              size="small"
              label={label}
              value={assistantRouting.contextRoutes[key]}
              onChange={(event) =>
                handleContextRouteChange(
                  key,
                  event.target.value as AssistantTarget,
                )
              }
              SelectProps={{ MenuProps: upwardMenuProps }}
            >
              <MenuItem value="local">Local</MenuItem>
              <MenuItem value="remote">Remote</MenuItem>
            </TextField>
          ))}
        </Box>
      )}

      <Box display="flex" gap={1}>
        <TextField
          value={message}
          onChange={(e) => setMessage(e.target.value)}
          fullWidth
          variant="outlined"
          placeholder="ROSAnnotator can help you annotate"
        />
        <Button onClick={handleSendMessage} variant="contained">
          Send
        </Button>
      </Box>
    </Box>
  );
};

export default Chatbox;
