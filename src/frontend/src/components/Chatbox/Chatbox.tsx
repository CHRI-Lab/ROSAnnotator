import React, { useState } from "react";
import Box from "@mui/material/Box";
import TextField from "@mui/material/TextField";
import Button from "@mui/material/Button";
import logo from "../../assets/rosannotator_logo.png";

const Chatbox = ({ onSendMessage }) => {
  const [message, setMessage] = useState("");
  const [chatHistory, setChatHistory] = useState([]);

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
            <strong>{msg.sender === "user" ? "You" : "ROSAnnotator"}:</strong> {msg.text}
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
