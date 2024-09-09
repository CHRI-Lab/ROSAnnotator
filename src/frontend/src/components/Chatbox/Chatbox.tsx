import React, { useState } from "react";
import Box from "@mui/material/Box";
import TextField from "@mui/material/TextField";
import Button from "@mui/material/Button";

const Chatbox = ({ onSendMessage }) => {
  const [message, setMessage] = useState("");
  const [chatHistory, setChatHistory] = useState([]);

  const handleSendMessage = () => {
    if (message.trim() !== "") {
      const newMessage = { sender: "user", text: message };
      setChatHistory([...chatHistory, newMessage]);
  
      // 调用父组件的 onSendMessage，并处理 GPT 的回复
      onSendMessage(message).then((gptResponse) => {
        const gptMessage = { sender: "gpt", text: gptResponse };
        setChatHistory((prevChatHistory) => [...prevChatHistory, gptMessage]);
      });
  
      setMessage(""); // 清空输入框
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
      height="100%" // 确保 Chatbox 占据整个父容器的高度
    >
      {/* 聊天历史 */}
      <Box flexGrow={1} overflow="auto" mb={2}>
        {chatHistory.map((msg, index) => (
          <Box key={index} mb={1} textAlign={msg.sender === "user" ? "right" : "left"}>
            <strong>{msg.sender === "user" ? "You" : "GPT"}:</strong> {msg.text}
          </Box>
        ))}
      </Box>
  
      {/* 输入框和发送按钮 */}
      <Box display="flex">
        <TextField
          value={message}
          onChange={(e) => setMessage(e.target.value)}
          fullWidth
          variant="outlined"
          placeholder="GPT can help you annotate"
        />
        <Button onClick={handleSendMessage} variant="contained" sx={{ ml: 1 }}>
          Send
        </Button>
      </Box>
    </Box>
  );
};

export default Chatbox;
