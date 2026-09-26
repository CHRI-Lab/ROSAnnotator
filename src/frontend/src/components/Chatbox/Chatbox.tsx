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
import Checkbox from "@mui/material/Checkbox";
import ListItemText from "@mui/material/ListItemText";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { AssistantRequestOptions } from "../../types/aiRecords";
import {
  AssistantTimeRange,
  formatChunkTime,
  validateChunkTimeRange,
} from "./timeRange";
import {
  AssistantMode,
  AssistantReply,
  AssistantRouting,
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
  duration: number;
  axes: Array<{ id: number; axisName?: string }>;
  onSendMessage: (
    message: string,
    assistantRouting: AssistantRouting,
    options?: AssistantRequestOptions,
  ) => Promise<AssistantReply>;
};

type PendingFallback = {
  message: string;
  reason: string;
  from: "local" | "remote";
  to: "local" | "remote";
  timeRange: AssistantTimeRange;
  timelineScope: { axisIds: number[]; allowNew: boolean };
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

const NEW_TIMELINE_VALUE = "new";

const Chatbox = ({ onSendMessage, duration, axes }: ChatboxProps) => {
  const [message, setMessage] = useState("");
  const [chatHistory, setChatHistory] = useState<ChatMessage[]>([]);
  const [initialAssistantRouting] = useState(loadAssistantRouting);
  const [assistantRouting, setAssistantRouting] = useState<AssistantRouting>(
    initialAssistantRouting ?? DEFAULT_ASSISTANT_ROUTING,
  );
  const [hasAssistantSelection, setHasAssistantSelection] = useState(
    initialAssistantRouting !== null,
  );
  const [pendingFallback, setPendingFallback] =
    useState<PendingFallback | null>(null);
  const [rangeStart, setRangeStart] = useState("00:00");
  const [rangeEnd, setRangeEnd] = useState(() => formatChunkTime(duration));
  const [timelineSelection, setTimelineSelection] = useState<string[]>([]);

  useEffect(() => {
    setRangeStart("00:00");
    setRangeEnd(formatChunkTime(duration));
  }, [duration]);

  const timeSelection = validateChunkTimeRange(rangeStart, rangeEnd, duration);

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
    setAssistantRouting({
      mode,
      contextRoutes: {
        transcript: mode,
        frames: mode,
        codebook: mode,
        timeline: mode,
      },
    });
  };

  const handleSendMessage = () => {
    if (message.trim() !== "" && timeSelection.range) {
      const submittedMessage = message;
      const submittedRange = timeSelection.range;
      const submittedTimelineScope = {
        axisIds: timelineSelection
          .filter((value) => value !== NEW_TIMELINE_VALUE)
          .map(Number)
          .filter(Number.isFinite),
        allowNew: timelineSelection.includes(NEW_TIMELINE_VALUE),
      };
      const newMessage: ChatMessage = { sender: "user", text: message };
      setChatHistory([...chatHistory, newMessage]);

      onSendMessage(submittedMessage, assistantRouting, {
        timeRange: submittedRange,
        timelineScope: submittedTimelineScope,
      }).then((assistantResponse) => {
        if (assistantResponse.canFallbackToRemote) {
          setPendingFallback({
            message: submittedMessage,
            reason: assistantResponse.text,
            from: "local",
            to: "remote",
            timeRange: submittedRange,
            timelineScope: submittedTimelineScope,
          });
          return;
        }
        if (assistantResponse.canFallbackToLocal) {
          setPendingFallback({
            message: submittedMessage,
            reason: assistantResponse.text,
            from: "remote",
            to: "local",
            timeRange: submittedRange,
            timelineScope: submittedTimelineScope,
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

  const handleFallback = () => {
    if (!pendingFallback) {
      return;
    }

    const fallbackRouting: AssistantRouting = {
      mode: pendingFallback.to,
      contextRoutes: {
        transcript: pendingFallback.to,
        frames: pendingFallback.to,
        codebook: pendingFallback.to,
        timeline: pendingFallback.to,
      },
    };
    const fallbackMessage = pendingFallback.message;
    const fallbackFrom = pendingFallback.from;
    const fallbackTo = pendingFallback.to;

    setPendingFallback(null);
    setHasAssistantSelection(true);
    setAssistantRouting(fallbackRouting);
    onSendMessage(fallbackMessage, fallbackRouting, {
      fallbackConsent: {
        from: fallbackFrom,
        to: fallbackTo,
        userConsented: true,
      },
      timeRange: pendingFallback.timeRange,
      timelineScope: pendingFallback.timelineScope,
    }).then((assistantResponse) => {
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

  const handleDeclineFallback = () => {
    if (!pendingFallback) {
      return;
    }

    setChatHistory((history) => [
      ...history,
      {
        sender: "gpt",
        text: pendingFallback.reason,
        assistantMode: pendingFallback.from,
        isError: true,
      },
    ]);
    setPendingFallback(null);
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
        open={pendingFallback !== null}
        onClose={handleDeclineFallback}
      >
        <DialogTitle>Switch to {formatAssistantMode(pendingFallback?.to)}?</DialogTitle>
        <DialogContent>
          <DialogContentText>
            {pendingFallback?.reason}{" "}
            {pendingFallback?.to === "remote"
              ? "Continuing with Remote will send the current transcript, video frames, codebook, and timeline context to OpenAI."
              : "Continuing with Local will retry the same request using the selected local model."}
          </DialogContentText>
        </DialogContent>
        <DialogActions>
          <Button onClick={handleDeclineFallback}>Keep Failed</Button>
          <Button onClick={handleFallback} variant="contained" autoFocus>
            Switch to {formatAssistantMode(pendingFallback?.to)}
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
        </TextField>
      </Box>

      <Box display="flex" gap={1} mb={1} alignItems="flex-start">
        <TextField
          size="small"
          label="Range start"
          value={rangeStart}
          onChange={(event) => setRangeStart(event.target.value)}
          error={Boolean(timeSelection.error)}
          inputProps={{ "aria-label": "AI range start", inputMode: "numeric" }}
          sx={{ width: 112 }}
        />
        <TextField
          size="small"
          label="Range end"
          value={rangeEnd}
          onChange={(event) => setRangeEnd(event.target.value)}
          error={Boolean(timeSelection.error)}
          inputProps={{ "aria-label": "AI range end", inputMode: "numeric" }}
          sx={{ width: 112 }}
        />
      </Box>
      <Box color={timeSelection.error ? "error.main" : "text.secondary"} fontSize="0.75rem" mb={1}>
        {timeSelection.error || `Chunk-relative range · 00:00–${formatChunkTime(duration)}`}
      </Box>

      <TextField
        select
        fullWidth
        size="small"
        label="AI timeline access"
        value={timelineSelection}
        onChange={(event) => {
          const value = event.target.value;
          setTimelineSelection(typeof value === "string" ? value.split(",") : value);
        }}
        SelectProps={{
          multiple: true,
          MenuProps: upwardMenuProps,
          renderValue: (selected) => {
            const values = selected as string[];
            if (values.length === 0) return "No timeline";
            return values.map((value) => {
              if (value === NEW_TIMELINE_VALUE) return "New timeline";
              const axis = axes.find((item) => item.id === Number(value));
              return axis?.axisName || `Timeline ${value}`;
            }).join(", ");
          },
        }}
        inputProps={{ "aria-label": "AI timeline access" }}
        sx={{ mb: 1 }}
      >
        {axes.map((axis) => {
          const value = String(axis.id);
          return (
            <MenuItem key={value} value={value}>
              <Checkbox checked={timelineSelection.includes(value)} />
              <ListItemText primary={axis.axisName || `Timeline ${axis.id}`} />
            </MenuItem>
          );
        })}
        <MenuItem value={NEW_TIMELINE_VALUE}>
          <Checkbox checked={timelineSelection.includes(NEW_TIMELINE_VALUE)} />
          <ListItemText primary="New timeline" />
        </MenuItem>
      </TextField>

      <Box display="flex" gap={1}>
        <TextField
          value={message}
          onChange={(e) => setMessage(e.target.value)}
          fullWidth
          variant="outlined"
          placeholder="ROSAnnotator can help you annotate"
        />
        <Button
          onClick={handleSendMessage}
          variant="contained"
          disabled={!message.trim() || !timeSelection.range}
        >
          Send
        </Button>
      </Box>
    </Box>
  );
};

export default Chatbox;
