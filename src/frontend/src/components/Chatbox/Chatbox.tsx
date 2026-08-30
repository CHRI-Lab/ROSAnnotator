import { useState } from "react";
import Box from "@mui/material/Box";
import TextField from "@mui/material/TextField";
import Button from "@mui/material/Button";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

type ChatMessage = {
  sender: "user" | "gpt";
  text: string;
};

type ChatboxProps = {
  onSendMessage: (message: string) => Promise<string>;
};

const Chatbox = ({ onSendMessage }: ChatboxProps) => {
  const [message, setMessage] = useState("");
  const [chatHistory, setChatHistory] = useState<ChatMessage[]>([]);

  const handleSendMessage = () => {
    if (message.trim() !== "") {
      const newMessage = { sender: "user", text: message };
      setChatHistory([...chatHistory, newMessage]);

      onSendMessage(message).then((gptResponse) => {
        const gptMessage = { sender: "gpt", text: gptResponse };
        setChatHistory((prevChatHistory) => [...prevChatHistory, gptMessage]);
      });

      setMessage(""); 
    }
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
      <Box flexGrow={1} overflow="auto" mb={2}>
        {chatHistory.map((msg, index) => (
          <Box key={index} mb={1} textAlign={msg.sender === "user" ? "right" : "left"}>
            <strong>{msg.sender === "user" ? "You" : "ROSAnnotator"}:</strong>
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
              <> {msg.text}</>
            )}
          </Box>
        ))}
      </Box>

      <Box display="flex">
        <TextField
          value={message}
          onChange={(e) => setMessage(e.target.value)}
          fullWidth
          variant="outlined"
          placeholder="ROSAnnotator can help you annotate"
        />
        <Button onClick={handleSendMessage} variant="contained" sx={{ ml: 1 }}>
          Send
        </Button>
      </Box>
    </Box>
  );
};

export default Chatbox;
