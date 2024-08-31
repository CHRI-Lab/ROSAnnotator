import { useState, useCallback, useEffect } from "react";
import ReactPlayer from "react-player";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import { Tabs, Tab } from "@mui/material";

import Timeline from "../../components/Timeline";
import Transcript from "../../components/Transcript";
import Booklist from "../../components/Booklist/Booklist";
import EditBooklistForm from "../../components/EditBooklistForm/EditBooklistForm";
import AnnotationTable from "../../components/AnnotationTable";
import { AxesProvider } from "../../components/AxesProvider/AxesContext";
import StatisticsAnnotation from "../../components/StatisticsAnnotation";
import StatisticsTier from "../../components/StatisticsTier";

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

  useEffect(() => {
    if (bookListData) {
      setBookList(bookListData);
    }
  }, []);

  const handleTabChange = (_event, newValue) => {
    setSelectedTab(newValue);
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
        setEditMode(false); // Exit edit mode after saving
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
      <Box
        display="flex"
        justifyContent="center"
        alignItems="center"
        flexDirection="column"
      >
        <Box
          display="flex"
          justifyContent="center"
          alignItems="center"
          flexDirection="row"
        >
          <Box width="100%" height={452} maxWidth={602} margin={1}>
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
          <Box width={600} height={452} overflow="auto" margin={1}>
            <Box sx={{ borderBottom: 1, borderColor: "divider" }}>
              <Tabs
                value={selectedTab}
                onChange={handleTabChange}
                aria-label="annotation tabs"
              >
                <Tab label="Annotations" />
                <Tab label="Transcript" />
                <Tab label="Booklist" />
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

        <Box width="100%" maxWidth={1200}>
          <Timeline
            rosBagFileName={rosBagFileName}
            bookListFileName={bookListFileName}
            duration={duration}
            played={played}
            onSeek={handleSeek}
            booklist={bookList}
            annotationData={data.annotation_data}
          />
        </Box>
      </Box>
    </AxesProvider>
  );
};

export default Annotator;
