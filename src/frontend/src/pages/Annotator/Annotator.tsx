import { useState, useCallback, useEffect } from "react";
import ReactPlayer from "react-player";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import { Tabs, Tab } from "@mui/material";

import Chatbox from "../../components/Chatbox";
import Timeline from "../../components/Timeline";
import Transcript from "../../components/Transcript";
import Booklist from "../../components/Booklist/Booklist";
import EditBooklistForm from "../../components/EditBooklistForm/EditBooklistForm";
import AnnotationTable from "../../components/AnnotationTable";
import { AxesProvider } from "../../components/AxesProvider/AxesContext";
import StatisticsAnnotation from "../../components/StatisticsAnnotation";
import StatisticsTier from "../../components/StatisticsTier";
import Axis from "../../components/Axis/Axis";

const Annotator = ({
  rosBagFileName,
  bookListFileName,
  data,
  bookListData,
}) => {
  const [player, setPlayer] = useState<ReactPlayer | null>(null);
  const [duration, setDuration] = useState(0);
  const [played, setPlayed] = useState(0);
  const [editMode, setEditMode] = useState(false);
  const [bookList, setBookList] = useState(bookListData);
  const [selectedTab, setSelectedTab] = useState(0);
  const [axes, setAxes] = useState([]);
  const [axesData, setAxesData] = useState([]);
  const [instruction, setInstruction] = useState(null);
  useEffect(() => {
    if (bookListData) {
      setBookList(bookListData);
    }

  }, [data, bookListData]);

  const handleTabChange = (_event, newValue) => {
    setSelectedTab(newValue);
  };

  const handleAxesUpdate = (updatedAxes) => {
    setAxesData(updatedAxes);
    return updatedAxes;
  };

  const handleSendMessageToGPT = (message) => {
    return fetch("http://localhost:8000/api/gpt_chat/", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        message: message, // 用户消息
        audio_transcript: data.audio_transcript, // 音频转录的文本
        Axeinfo: axesData,
      }),
    })
      .then((response) => {
        // 检查响应是否成功
        if (!response.ok) {
          return response.text().then((text) => {
            throw new Error(`Error ${response.status}: ${text}`);
          });
        }
        return response.json();
      })
      .then((data) => {
        const responseString = data.response; // GPT 返回的响应
  
        try {
          // 尝试解析字符串为 JSON
          const parsedObject = JSON.parse(responseString);
  
          // 检查解析后的对象是否为指令
          if (parsedObject.type === "instruction" && Array.isArray(parsedObject.steps)) {
            console.log("This is an instruction:", parsedObject);
            setInstruction(parsedObject);
            return "Done"; // 返回指令已完成
          } else {
            // 如果解析成功但不是指令，返回普通语句
            return responseString; // 返回普通对话
          }
        } catch (error) {
          // 如果解析失败，则认为是普通字符串
          console.log("This is a normal message:", responseString);
          return responseString; // 返回普通对话
        }
      });
  };



  const handleSaveBooklist = (jsonData) => {
    setBookList(jsonData);
    fetch("http://localhost:8000/api/update_booklist/", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: bookListFileName, data: jsonData }),
    })
      .then((response) => response.json())
      .then((data) => {
        console.log("Success:", data);
        alert("Data saved successfully!");
        setEditMode(false);
      })
      .catch((error) => {
        console.error("Error:", error);
        alert("Failed to save data.");
      });
  };

  const handleOnEdit = () => {
    setEditMode(true);
  };

  const playerRef = useCallback((playerInstance: ReactPlayer) => {
    setPlayer(playerInstance);
  }, []);

  const handleSeek = useCallback((time: number) => {
    setPlayed(time);
    if (player) {
      player.seekTo(time);
    }
  }, [player]);

  return (
    <AxesProvider>
      <Box display="flex" height="100vh" overflow="hidden">
        {/* 左侧的主内容区域 */}
        <Box
          display="flex"
          justifyContent="center"
          alignItems="center"
          flexDirection="column"
          flex={0.7}
          height="100%"  
          overflow="auto"
        >
          <Box
            display="flex"
            justifyContent="center"
            alignItems="center"
            flexDirection="row"
            flex="1 1 auto"
            overflow="auto"
          >
            <Box width="100%" flexGrow={1} maxWidth={602} margin={1}>
              <ReactPlayer
                ref={playerRef}
                width="100%"
                height="auto"
                url={`/public/processed/${data.video_path}`}
                onDuration={setDuration}
                onProgress={({ playedSeconds }) => setPlayed(playedSeconds)}
                controls
                playing
              />
            </Box>
            <Box width={600} flexGrow={1} overflow="auto" margin={1} maxHeight="50vh">
              <Box sx={{ borderBottom: 1, borderColor: "divider" }}>
                <Tabs
                  value={selectedTab}
                  onChange={handleTabChange}
                  aria-label="annotation tabs"
                >
                  <Tab label="Annotations" />
                  <Tab label="Transcript" />
                  <Tab label="Codebook" />
                  <Tab label="Statistics (Annotations)" />
                  <Tab label="Statistics (Tiers)" />
                </Tabs>
              </Box>
              {selectedTab === 0 && <AnnotationTable />}
              {selectedTab === 1 && (
                <Transcript
                  LRC={data.audio_transcript}
                  played={played}
                  setPlayed={handleSeek}
                />
              )}
              {selectedTab === 2 &&
                (editMode ? (
                  <EditBooklistForm
                    bookListData={bookList}
                    onSave={handleSaveBooklist}
                  />
                ) : (
                  <Box>
                    <Button
                      onClick={handleOnEdit}
                      variant="contained"
                      sx={{ marginTop: 2 }}
                    >
                      Edit
                    </Button>
                    <Booklist bookListData={bookList} />
                  </Box>
                ))}
              {selectedTab === 3 && <StatisticsAnnotation />}
              {selectedTab === 4 && <StatisticsTier />}
            </Box>
          </Box>
  
          {/* 包裹 Timeline 的容器，添加滚动条 */}
          <Box width="100%" maxWidth={1200} overflow="auto" maxHeight="50vh">
            <Timeline
              rosBagFileName={rosBagFileName}
              bookListFileName={bookListFileName}
              duration={duration}
              played={played}
              onSeek={handleSeek}
              booklist={bookList}
              annotationData={data.annotation_data}
              speakerData={data.speaker_data}
              onAxesUpdate={handleAxesUpdate}
              instruction={instruction}
            />
          </Box>
        </Box>
  
        {/* 右侧的 Chatbox 区域 */}
        <Box
          flex={0.3}
          height="100%"
          bgcolor="background.paper"
          borderLeft={1}
          borderColor="divider"
          display="flex"
          flexDirection="column"
          justifyContent="space-between"
          overflow="auto"
        >
          <Chatbox onSendMessage={handleSendMessageToGPT} />
        </Box>
      </Box>
    </AxesProvider>
  );
};

export default Annotator;
