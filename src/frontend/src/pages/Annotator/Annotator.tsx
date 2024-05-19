import React, { useState, useCallback } from "react";
import ReactPlayer from "react-player";
import Box from "@mui/material/Box";
import { createTheme, ThemeProvider } from "@mui/material/styles";
import Button from "@mui/material/Button";
import { Dialog, DialogActions, DialogContent, Grid, Tabs, Tab } from "@mui/material";

import Timeline from "../../components/Timeline";
import Transcript from "../../components/Transcript";
import Booklist from "../../components/Booklist/Booklist";
import EditBooklistForm from "../../components/EditBooklistForm/EditBooklistForm";
import AnnotationTable from "../../components/AnnotationTable";
import { AxesProvider } from "../../components/AxesProvider/AxesContext";

import bookListDataTest from "../../../public/predefined_booklist.json";

const theme = createTheme();

interface AnnotatorProps {
  bookListFileName: string;
  bookListData: Record<string, string[]>;
}

const Annotator: React.FC<AnnotatorProps> = ({
  bookListFileName,
  bookListData,
}) => {
  const [player, setPlayer] = useState<ReactPlayer | null>(null);
  const [duration, setDuration] = useState(0);
  const [played, setPlayed] = useState(0);
  const [open, setOpen] = useState(false);
  const [editMode, setEditMode] = useState(false);
  const [bookList, setBookList] = useState(bookListDataTest); //TODO Replace with bookListData
  const [selectedTab, setSelectedTab] = useState(0);

  const handleTabChange = (event, newValue) => {
    setSelectedTab(newValue);
  };

  // TODO Method API Call
  const handleSaveBooklist = (jsonData: any) => {
    setBookList(jsonData);
    console.log(jsonData);
    fetch("/api/.../saveBooklist", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        booklist_filename: bookListFileName,
        booklist_data: jsonData,
      }),
    })
      .then((response) => response.json())
      .then((data) => {
        console.log("Success:", data);
        alert("Data saved successfully!");
      })
      .catch((error) => {
        console.error("Error:", error);
        alert("Failed to save data.");
      });
  };

  const handleDuration = (duration: number) => {
    setDuration(duration);
  };

  const handleClickOpen = () => {
    setOpen(true);
    setEditMode(false);
  };

  const handleClose = () => {
    setOpen(false);
  };

  const handleProgress = (progress: { playedSeconds: number }) => {
    if (!isNaN(progress.playedSeconds)) {
      setPlayed(progress.playedSeconds);
    }
  };

  const handleSeek = useCallback(
    (time: number) => {
      setPlayed(time);
      if (player) {
        player.seekTo(time);
      }
    },
    [player]
  );

  const playerRef = useCallback((playerInstance: ReactPlayer) => {
    setPlayer(playerInstance);
  }, []);

  const handleOnEdit = () => {
    setEditMode(true);
  };

  return (
    <ThemeProvider theme={theme}>
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
            <Box width="100%" height={452} maxWidth={602}>
              <ReactPlayer
                ref={playerRef}
                width="100%"
                height="auto"
                url="sample.mp4"
                onDuration={handleDuration}
                onProgress={handleProgress}
                controls
                playing
              />
            </Box>
            <Box width={600} height={452} overflow="auto">
              <Box sx={{ borderBottom: 1, borderColor: 'divider' }}>
                <Tabs value={selectedTab} onChange={handleTabChange} aria-label="annotation tabs">
                  <Tab label="Annotations" />
                  <Tab label="Transcript" />
                </Tabs>
              </Box>
              {selectedTab === 0 && <AnnotationTable />}
              {selectedTab === 1 && <Transcript played={played} setPlayed={handleSeek}/>}
            </Box>
          </Box>
          <div>
            <Box sx={{ position: "absolute", top: 0, left: 0, padding: 2 }}>
              <Button variant="outlined" onClick={handleClickOpen}>
                Booklist
              </Button>
              <Dialog open={open} onClose={handleClose} maxWidth="md" fullWidth>
                <DialogContent>
                  <Grid container spacing={2}>
                    {editMode ? (
                      <EditBooklistForm
                        bookListData={bookList}
                        onSave={handleSaveBooklist}
                      />
                    ) : (
                      <Booklist bookListData={bookList} />
                    )}
                  </Grid>
                </DialogContent>
                <DialogActions>
                  {!editMode && <Button onClick={handleOnEdit}>Edit</Button>}
                  <Button onClick={handleClose}>Close</Button>
                </DialogActions>
              </Dialog>
            </Box>
          </div>

          <Box width="100%" maxWidth={1200}>
            <Timeline
              duration={duration}
              played={played}
              annotations={bookList}
              onSeek={handleSeek}
            />
          </Box>
        </Box>
      </AxesProvider>
    </ThemeProvider>
  );
};

export default Annotator;
