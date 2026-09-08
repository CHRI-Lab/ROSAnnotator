import {
  List,
  ListItem,
  ListItemText,
  Paper,
  Typography,
  Button,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogContentText,
  DialogActions,
} from "@mui/material";
import Snackbar from "@mui/material/Snackbar";
import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
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
  const [rosSelectedIndex, setRosSelectedIndex] = useState(null);
  const [bookSelectedIndex, setBookSelectedIndex] = useState(null);
  const [annotSelectedIndex, setAnnotSelectedIndex] = useState(null);
  const [open, setOpen] = useState(false);

  // AUTOSAVE RECOVERY
  const [autosaveMeta, setAutosaveMeta] = useState<AutosaveMeta | null>(null);
  const [isRestoreDialogOpen, setIsRestoreDialogOpen] = useState(false);
  // Tracks the bag currently selected, so a slow check for a previously
  // selected bag cannot land after the user has moved on to another one.
  const selectedBagRef = useRef("");

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

  // Selecting a bag prefetches its autosave metadata, so the prompt appears
  // without a wait when the user clicks Load Me. Metadata only, no axes.
  const handleSelectRosBag = (fileName: string, index: number) => {
    setRosBagFile(fileName);
    setRosSelectedIndex(index);
    setAutosaveMeta(null);
    selectedBagRef.current = fileName;

    fetchAutosaveMeta(fileName)
      .then((meta) => {
        if (selectedBagRef.current !== fileName) return;
        setAutosaveMeta(meta.exists ? meta : null);
      })
      .catch((error) => {
        // No autosave information just means no prompt. Never block loading.
        console.warn("Could not check for an autosave.", error);
      });
  };

  const goToMainPage = (restore: boolean) => {
    const booklistPath = bookListFile ? "/book/" + bookListFile : "";
    const annotationPath = annotationFile
      ? "/annotation/" + annotationFile
      : "";
    const restoreQuery = restore ? "?restore=autosave" : "";
    navigate(
      "/main/" + rosBagFile + booklistPath + annotationPath + restoreQuery
    );
  };

  const handleLoadData = () => {
    if (rosBagFile === "") {
      setOpen(true);
      return;
    }

    if (autosaveMeta?.exists && autosaveMeta.bag_filename === rosBagFile) {
      setIsRestoreDialogOpen(true);
      return;
    }

    goToMainPage(false);
  };

  const handleRestoreAutosave = () => {
    setIsRestoreDialogOpen(false);
    goToMainPage(true);
  };

  const handleDiscardAutosave = async () => {
    setIsRestoreDialogOpen(false);
    try {
      await deleteAutosave(rosBagFile);
    } catch (error) {
      // The recovery file surviving is a smaller problem than blocking the
      // user here. The next autosave overwrites it anyway.
      console.warn("Could not delete the autosave.", error);
    }
    setAutosaveMeta(null);
    goToMainPage(false);
  };

  const handleClose = (event?: React.SyntheticEvent, reason?: string) => {
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
          </List>
        </Paper>
      </div>

      <div
        style={{ display: "flex", justifyContent: "center", marginTop: "20px" }}
      >
        <Button variant="contained" color="primary" onClick={handleLoadData}>
          Load Me
        </Button>
      </div>

      <Dialog
        open={isRestoreDialogOpen}
        onClose={() => setIsRestoreDialogOpen(false)}
      >
        <DialogTitle>Unsaved work found</DialogTitle>
        <DialogContent>
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
          <Button onClick={handleDiscardAutosave} color="error">
            Discard and start fresh
          </Button>
          <Button onClick={handleRestoreAutosave} variant="contained">
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
