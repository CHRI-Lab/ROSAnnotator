import {
  List,
  ListItem,
  ListItemText,
  Paper,
  Typography,
  Button,
  Alert,
  CircularProgress,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControlLabel,
  Radio,
  RadioGroup,
  TextField,
} from "@mui/material";
import Snackbar from "@mui/material/Snackbar";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { createChunkManifest, inspectInput } from "../../api/chunks";

function LoadableList() {
  const [fileNameList, setFileNameList] = useState({
    rosbag_files: [],
    booklist_files: [],
    annotation_files: [],
  });
  const [rosBagFile, setRosBagFile] = useState("");
  const [bookListFile, setBookListFile] = useState("");
  const [annotationFile, setAnnotationFile] = useState("");
  const [rosSelectedIndex, setRosSelectedIndex] = useState<number | null>(null);
  const [bookSelectedIndex, setBookSelectedIndex] = useState<number | null>(null);
  const [annotSelectedIndex, setAnnotSelectedIndex] = useState<number | null>(null);
  const [open, setOpen] = useState(false);
  const [chunkDialogOpen, setChunkDialogOpen] = useState(false);
  const [chunkingEnabled, setChunkingEnabled] = useState(true);
  const [chunkMinutes, setChunkMinutes] = useState("5");
  const [inputDurationSeconds, setInputDurationSeconds] = useState(0);
  const [chunkError, setChunkError] = useState("");
  const [preparing, setPreparing] = useState(false);

  const navigate = useNavigate();

  useEffect(() => {
    const fetchData = async () => {
      try {
        const response = await fetch("http://localhost:8000/api/list_filenames", {
          method: "GET",
          headers: {
            "Content-Type": "application/json",
          },
        });
        const data = await response.json();
        setFileNameList({
          rosbag_files: data.rosbag_files,
          booklist_files: data.booklist_files,
          annotation_files: data.annotation_files,
        });
        console.log(data)
      } catch (error) {
        console.log(error);
      }
    };

    fetchData();
  }, []);

  const destinationPath = () => {
    const booklistPath = bookListFile ? "/book/" + encodeURIComponent(bookListFile) : "";
    const annotationPath = annotationFile
      ? "/annotation/" + encodeURIComponent(annotationFile)
      : "";
    return "/main/" + encodeURIComponent(rosBagFile) + booklistPath + annotationPath;
  };

  const handleLoadData = async () => {
    if (rosBagFile === "") {
      setOpen(true);
      return;
    }
    setPreparing(true);
    setChunkError("");
    try {
      const inspection = await inspectInput(rosBagFile);
      setInputDurationSeconds(inspection.duration_seconds);
      const suggestedMinutes = Math.max(
        1,
        Math.min(5, Math.floor(inspection.duration_minutes - 0.001))
      );
      setChunkMinutes(String(suggestedMinutes));
      setChunkingEnabled(inspection.duration_seconds > 60);
      setChunkDialogOpen(true);
    } catch (error) {
      setChunkError(error instanceof Error ? error.message : "Unable to inspect ROSBag.");
      setChunkDialogOpen(true);
    } finally {
      setPreparing(false);
    }
  };

  const handleConfirmChunking = async () => {
    const seconds = Number(chunkMinutes) * 60;
    if (chunkingEnabled && (!Number.isFinite(seconds) || seconds <= 0 || seconds >= inputDurationSeconds)) {
      setChunkError("Chunk length must be greater than 0 and shorter than the input.");
      return;
    }
    setPreparing(true);
    setChunkError("");
    try {
      const manifest = await createChunkManifest({
        bagFilename: rosBagFile,
        booklistFilename: bookListFile,
        annotationFilename: annotationFile,
        chunkingEnabled,
        chunkSeconds: chunkingEnabled ? seconds : undefined,
      });
      navigate(`${destinationPath()}?manifestId=${encodeURIComponent(manifest.id)}`);
    } catch (error) {
      setChunkError(error instanceof Error ? error.message : "Unable to create chunks.");
    } finally {
      setPreparing(false);
    }
  };

  const handleClose = (_event: Event | React.SyntheticEvent, reason?: string) => {
    if (reason === "clickaway") {
      return;
    }
    setOpen(false);
  };

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        justifyContent: "center",
        height: "100vh",
        // padding: "20px",
        // marginTop: "200px",
      }}
    >
      <div style={{ display: "flex", justifyContent: "space-around" }}>
        <Paper style={{ width: "30%" }}>
          <Typography
            variant="h6"
            component="h2"
            style={{ fontWeight: "bold", textAlign: "center" }}
          >
            ROSBAG DATA FILE *
          </Typography>
          <List component="nav" aria-label="ROSbag data file">
            {fileNameList.rosbag_files.length === 0 ? (
              <ListItem button>
                <ListItemText primary="No file found. Please place your files in the prescribed location." />
              </ListItem>
            ) : (
              fileNameList.rosbag_files.map((fileName, index) => (
                <ListItem
                  button
                  key={index}
                  onClick={() => {
                    setRosBagFile(fileName);
                    setRosSelectedIndex(index);
                  }}
                  selected={rosSelectedIndex === index}
                >
                  <ListItemText
                    primary={fileName}
                    primaryTypographyProps={{
                      style: {
                        overflow: "hidden",
                        textOverflow: "ellipsis",
                        whiteSpace: "nowrap",
                        width: "100%",
                      },
                    }}
                  />
                </ListItem>
              ))
            )}
          </List>
        </Paper>

        <Paper style={{ width: "30%" }}>
          <Typography
            variant="h6"
            component="h2"
            style={{ fontWeight: "bold", textAlign: "center" }}
          >
            Predefined Codebook
          </Typography>
          <List component="nav" aria-label="Predefined Codebook">
            {fileNameList.booklist_files.length === 0 ? (
              <ListItem button>
                <ListItemText primary="No file found. Please place your files in the prescribed location." />
              </ListItem>
            ) : (
              fileNameList.booklist_files.map((fileName, index) => (
                <ListItem
                  button
                  key={index}
                  onClick={() => {
                    setBookListFile(fileName);
                    setBookSelectedIndex(index);
                  }}
                  selected={bookSelectedIndex === index}
                >
                  <ListItemText
                    primary={fileName}
                    primaryTypographyProps={{
                      style: {
                        overflow: "hidden",
                        textOverflow: "ellipsis",
                        whiteSpace: "nowrap",
                        width: "100%",
                      },
                    }}
                  />
                </ListItem>
              ))
            )}
          </List>
        </Paper>

        <Paper style={{ width: "30%" }}>
          <Typography
            variant="h6"
            component="h2"
            style={{ fontWeight: "bold", textAlign: "center" }}
          >
            Annotation File
          </Typography>
          <List component="nav" aria-label="Annotation File">
            {fileNameList.annotation_files.map((fileName, index) => (
              <ListItem
                button
                key={index}
                onClick={() => {
                  setAnnotationFile(fileName);
                  setAnnotSelectedIndex(index);
                }}
                selected={annotSelectedIndex === index}
              >
                <ListItemText
                  primary={fileName}
                  primaryTypographyProps={{
                    style: {
                      overflow: "hidden",
                      textOverflow: "ellipsis",
                      whiteSpace: "nowrap",
                      width: "100%",
                    },
                  }}
                />
              </ListItem>
            ))}
            {/* <ListItem button>
              <ListItemText primary="Not Supported for Now" />
            </ListItem> */}
          </List>
        </Paper>
      </div>

      <div
        style={{ display: "flex", justifyContent: "center", marginTop: "20px" }}
      >
        <Button variant="contained" color="primary" onClick={handleLoadData} disabled={preparing}>
          {preparing ? <CircularProgress size={22} /> : "Load Me"}
        </Button>
      </div>

      <Dialog open={chunkDialogOpen} onClose={() => !preparing && setChunkDialogOpen(false)} fullWidth maxWidth="xs">
        <DialogTitle>Choose video chunking</DialogTitle>
        <DialogContent>
          <Typography color="text.secondary" sx={{ mb: 2 }}>
            Input length: {Math.floor(inputDurationSeconds / 60)}m {Math.round(inputDurationSeconds % 60)}s
          </Typography>
          <RadioGroup
            value={chunkingEnabled ? "chunk" : "whole"}
            onChange={(event) => setChunkingEnabled(event.target.value === "chunk")}
          >
            <FormControlLabel value="chunk" control={<Radio />} label="Split into chunks" />
            <FormControlLabel value="whole" control={<Radio />} label="Use the whole input" />
          </RadioGroup>
          {chunkingEnabled && (
            <TextField
              autoFocus
              fullWidth
              type="number"
              label="Chunk length (minutes)"
              value={chunkMinutes}
              onChange={(event) => setChunkMinutes(event.target.value)}
              inputProps={{ min: 0.1, step: 0.5 }}
              sx={{ mt: 2 }}
            />
          )}
          {chunkError && <Alert severity="error" sx={{ mt: 2 }}>{chunkError}</Alert>}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setChunkDialogOpen(false)} disabled={preparing}>Cancel</Button>
          <Button onClick={handleConfirmChunking} variant="contained" disabled={preparing || inputDurationSeconds <= 0}>
            {preparing ? <CircularProgress size={22} /> : "Continue"}
          </Button>
        </DialogActions>
      </Dialog>

      <Snackbar
        anchorOrigin={{ vertical: "top", horizontal: "center" }}
        open={open}
        autoHideDuration={6000}
        onClose={handleClose}
        message="ROSBag data file must be selected!"
      />
    </div>
  );
}

export default LoadableList;
