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
  MenuItem,
  DialogContentText,
} from "@mui/material";
import Snackbar from "@mui/material/Snackbar";
import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { createChunkManifest, inspectInput } from "../../api/chunks";
import {
  fetchAutosaveMeta,
  deleteAutosave,
  formatAutosaveTimestamp,
  AutosaveMeta,
} from "../../components/Autosave/autosaveUtils";

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
  const [sensorTopics, setSensorTopics] = useState<{ wrench: string[] }>({ wrench: [] });
  const [selectedSensorTopics, setSelectedSensorTopics] = useState<{ wrench: string[] }>({ wrench: [] });

  // AUTOSAVE RECOVERY
  const [autosaveMeta, setAutosaveMeta] = useState<AutosaveMeta | null>(null);
  const [isRestoreDialogOpen, setIsRestoreDialogOpen] = useState(false);
  const [recoveryError, setRecoveryError] = useState("");
  // Tracks the bag currently selected, so a slow check for a previously
  // selected bag cannot land after the user has moved on to another one.
  const selectedBagRef = useRef("");
  const autosaveCheckRef = useRef<Promise<AutosaveMeta | null> | null>(null);
  const operationInProgress = useRef(false);

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

  const prepareChunking = async () => {
    if (rosBagFile === "") {
      setOpen(true);
      return;
    }
    setPreparing(true);
    setChunkError("");
    setInputDurationSeconds(0);
    try {
      const inspection = await inspectInput(rosBagFile);
      const topics = inspection.topics || [];
      const sensors = {
        wrench: topics.filter(t => t.message_count > 0 && t.message_type === 'geometry_msgs/WrenchStamped').map(t => t.name),
      };
      setSensorTopics(sensors);
      setSelectedSensorTopics(sensors);
      if (inspection.duration_seconds === 0) {
        throw new Error('No supported data: this bag contains no messages or has zero duration. Please select another bag.');
      }
      if (!Number.isFinite(inspection.duration_seconds) || inspection.duration_seconds <= 0) {
        throw new Error("Unable to determine the input duration.");
      }
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

  // Selecting a bag prefetches its autosave metadata, so the prompt appears
  // without a wait when the user clicks Load Me. Metadata only, no axes.
  const handleSelectRosBag = (fileName: string, index: number) => {
    if (operationInProgress.current) return;
    setRosBagFile(fileName);
    setRosSelectedIndex(index);
    setAutosaveMeta(null);
    setRecoveryError("");
    selectedBagRef.current = fileName;

    const check = fetchAutosaveMeta(fileName)
      .then((meta) => {
        const result = meta.exists && meta.bag_filename === fileName ? meta : null;
        if (autosaveCheckRef.current === check) setAutosaveMeta(result);
        return result;
      })
      .catch((error) => {
        // No autosave information just means no prompt. Never block loading.
        console.warn("Could not check for an autosave.", error);
        return null;
      });
    autosaveCheckRef.current = check;
  };

  const goToRestoredSession = async () => {
    const manifest = await createChunkManifest({
      bagFilename: rosBagFile,
      booklistFilename: bookListFile,
      annotationFilename: annotationFile,
      chunkingEnabled: false,
    });
    navigate(
      `${destinationPath()}?manifestId=${encodeURIComponent(manifest.id)}&restore=autosave`
    );
  };

  const goToMainPage = (restore: boolean) => {
    if (restore) {
      return goToRestoredSession();
    }
    return prepareChunking();
  };

  const handleLoadData = async () => {
    if (operationInProgress.current) return;
    if (rosBagFile === "") {
      setOpen(true);
      return;
    }

    operationInProgress.current = true;
    setPreparing(true);
    try {
      // A quick click on Load must still wait for the selected bag's check.
      const meta = await autosaveCheckRef.current;
      if (selectedBagRef.current !== rosBagFile) return;
      if (meta?.exists) {
        setAutosaveMeta(meta);
        setRecoveryError("");
        setIsRestoreDialogOpen(true);
        return;
      }
      await goToMainPage(false);
    } finally {
      operationInProgress.current = false;
      setPreparing(false);
    }
  };

  const handleRestoreAutosave = async () => {
    if (operationInProgress.current) return;
    operationInProgress.current = true;
    setPreparing(true);
    setRecoveryError("");
    try {
      await goToMainPage(true);
      setIsRestoreDialogOpen(false);
    } catch (error) {
      setRecoveryError(
        "Could not prepare the saved session. Please try again, or discard the saved work to start fresh."
      );
    } finally {
      operationInProgress.current = false;
      setPreparing(false);
    }
  };

  const handleDiscardAutosave = async () => {
    if (operationInProgress.current) return;
    operationInProgress.current = true;
    setPreparing(true);
    setRecoveryError("");
    try {
      await deleteAutosave(rosBagFile);
      setAutosaveMeta(null);
      autosaveCheckRef.current = Promise.resolve(null);
      setIsRestoreDialogOpen(false);
      await goToMainPage(false);
    } catch (error) {
      setRecoveryError("Could not discard the saved work. Please try again or restore it.");
    } finally {
      operationInProgress.current = false;
      setPreparing(false);
    }
  };

  const handleConfirmChunking = async () => {
    if (operationInProgress.current || inputDurationSeconds <= 0) return;
    const seconds = Number(chunkMinutes) * 60;
    if (chunkingEnabled && (!Number.isFinite(seconds) || seconds <= 0 || seconds >= inputDurationSeconds)) {
      setChunkError("Chunk length must be greater than 0 and shorter than the input.");
      return;
    }
    operationInProgress.current = true;
    setPreparing(true);
    setChunkError("");
    try {
      const manifest = await createChunkManifest({
        bagFilename: rosBagFile,
        booklistFilename: bookListFile,
        annotationFilename: annotationFile,
        chunkingEnabled,
        chunkSeconds: chunkingEnabled ? seconds : undefined,
        viewOptions: {
          ...(sensorTopics.wrench.length ? { wrench: { topics: selectedSensorTopics.wrench } } : {}),
        },
      });
      navigate(`${destinationPath()}?manifestId=${encodeURIComponent(manifest.id)}`);
    } catch (error) {
      setChunkError(error instanceof Error ? error.message : "Unable to create chunks.");
    } finally {
      operationInProgress.current = false;
      setPreparing(false);
    }
  };

  const handleClose = (_event: Event | React.SyntheticEvent, reason?: string) => {
    if (reason === "clickaway") {
      return;
    }
    setOpen(false);
  };

  const autosaveCodebook = autosaveMeta?.booklist_filename || "";
  const codebookMismatch =
    Boolean(autosaveMeta) && autosaveCodebook !== (bookListFile || "");

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        justifyContent: "center",
        height: "100vh",
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
                  onClick={() => handleSelectRosBag(fileName, index)}
                  disabled={preparing}
                  selected={rosSelectedIndex === index}
                >
                  <ListItemText
                    primary={fileName}
                    secondary={
                      rosSelectedIndex === index && autosaveMeta?.exists
                        ? `Unsaved work from ${formatAutosaveTimestamp(
                            autosaveMeta.saved_at
                          )}`
                        : undefined
                    }
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
                  disabled={preparing}
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
                disabled={preparing}
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
            <>
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
              <Alert severity="warning" sx={{ mt: 2 }}>
                <Typography>
                  Speaker labels are assigned separately for each chunk. The same
                  speaker may have different labels across chunks, and the same
                  label may refer to different speakers. Check speaker identities
                  before combining annotations.
                </Typography>
                <Typography sx={{ mt: 1 }}>
                  An annotation block that crosses a chunk boundary will be
                  automatically split into separate blocks permanently.
                </Typography>
              </Alert>
            </>
          )}
          {(['wrench'] as const).filter(id => sensorTopics[id].length > 0).map(id => (
            <TextField key={id} select fullWidth sx={{ mt: 2 }} label="Force / Torque topics"
              value={selectedSensorTopics[id]} SelectProps={{ multiple: true }}
              onChange={e => setSelectedSensorTopics(previous => ({ ...previous, [id]: typeof e.target.value === 'string' ? e.target.value.split(',') : e.target.value }))}>
              {sensorTopics[id].map(topic => <MenuItem key={topic} value={topic}>{topic}</MenuItem>)}
            </TextField>
          ))}
          {chunkError && <Alert severity="error" sx={{ mt: 2 }}>{chunkError}</Alert>}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setChunkDialogOpen(false)} disabled={preparing}>Cancel</Button>
          <Button onClick={handleConfirmChunking} variant="contained" disabled={preparing || inputDurationSeconds <= 0}>
            {preparing ? <CircularProgress size={22} /> : "Continue"}
          </Button>
        </DialogActions>
      </Dialog>

      <Dialog
        open={isRestoreDialogOpen}
        onClose={() => !preparing && setIsRestoreDialogOpen(false)}
      >
        <DialogTitle>Unsaved work found</DialogTitle>
        <DialogContent>
          {recoveryError && <Alert severity="error">{recoveryError}</Alert>}
          <DialogContentText>
            {`ROSAnnotator has unsaved work for ${rosBagFile} from ${formatAutosaveTimestamp(
              autosaveMeta?.saved_at
            )}, with ${autosaveMeta?.axis_count ?? 0} time ${
              autosaveMeta?.axis_count === 1 ? "axis" : "axes"
            } and ${autosaveMeta?.block_count ?? 0} annotations.`}
          </DialogContentText>
          {codebookMismatch && (
            <DialogContentText sx={{ marginTop: 2 }}>
              {autosaveCodebook
                ? `This work was annotated against ${autosaveCodebook}, which is not the codebook you selected.`
                : "This work was annotated without a codebook."}
            </DialogContentText>
          )}
          {autosaveMeta?.recovered_from_backup && (
            <DialogContentText sx={{ marginTop: 2 }}>
              The most recent copy could not be read, so this is the previous
              one. Some recent edits may be missing.
            </DialogContentText>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={handleDiscardAutosave} color="error" disabled={preparing}>
            Discard and start fresh
          </Button>
          <Button onClick={handleRestoreAutosave} variant="contained" disabled={preparing}>
            Restore work
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
