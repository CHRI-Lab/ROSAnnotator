import React, { useState, useCallback } from "react";
import ReactPlayer from "react-player";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import { Grid, Tabs, Tab } from "@mui/material";

import Timeline from "../../components/Timeline";
import Transcript from "../../components/Transcript";
import Booklist from "../../components/Booklist/Booklist";
import EditBooklistForm from "../../components/EditBooklistForm/EditBooklistForm";
import AnnotationTable from "../../components/AnnotationTable";
import { AxesProvider } from "../../components/AxesProvider/AxesContext";

import bookListDataTest from "../../../public/predefined_booklist.json";

const Annotator = ({ rosBagFileName, bookListFileName, bookListData }) => {
  const [_, setPlayer] = useState<ReactPlayer | null>(null);
  const [duration, setDuration] = useState(0);
  const [played, setPlayed] = useState(0);
  const [editMode, setEditMode] = useState(false);
  const [bookList, setBookList] = useState(bookListDataTest);
  const [selectedTab, setSelectedTab] = useState(0);

  const handleTabChange = (_event, newValue) => {
    setSelectedTab(newValue);
  };

  const handleSaveBooklist = (jsonData) => {
    setBookList(jsonData);
    fetch("http://0.0.0.0:8000/api/update_booklist/", {
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
              url="/processed/record_2024_03_27_10_51_34.bag_2024-05-19-13:12:29/output.mp4"
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
              </Tabs>
            </Box>
            {selectedTab === 0 && <AnnotationTable />}
            {selectedTab === 1 && (
              <Transcript
                played={played}
                setPlayed={(time) => setPlayed(time)}
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
          </Box>
        </Box>

        <Box width="100%" maxWidth={1200}>
          <Timeline
            rosBagFileName={rosBagFileName}
            bookListFileName={bookListFileName}
            duration={duration}
            played={played}
            annotations={bookList}
            onSeek={(time) => setPlayed(time)}
          />
        </Box>
      </Box>
    </AxesProvider>
  );
};

export default Annotator;
