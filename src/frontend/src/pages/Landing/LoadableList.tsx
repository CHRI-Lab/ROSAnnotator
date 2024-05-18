import {
  List,
  ListItem,
  ListItemText,
  Paper,
  Typography,
  Button,
} from "@mui/material";
import Snackbar from "@mui/material/Snackbar";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

function LoadableList() {
  const [fileNameList, setFileNameList] = useState({
    rosbag_files: [],
    booklist_files: [],
    annotation_files: [],
  });
  const [rosBagFile, setRosBagFile] = useState("");
  const [bookListFile, setBookListFile] = useState("");
  // const [annotationFile, setAnnotationFile] = useState("");
  const [rosSelectedIndex, setRosSelectedIndex] = useState(null);
  const [bookSelectedIndex, setBookSelectedIndex] = useState(null);
  // const [annotSelectedIndex, setAnnotSelectedIndex] = useState(null);
  const [open, setOpen] = useState(false);

  const navigate = useNavigate();

  useEffect(() => {
    const fetchData = async () => {
      try {
        const response = await fetch(
          "http://localhost:8000/api/list_filenames"
        );
        const data = await response.json();
        console.log(data);
        setFileNameList({
          rosbag_files: data.rosbag_files,
          booklist_files: data.booklist_files,
          annotation_files: data.annotation_files,
        });
      } catch (error) {
        console.error(error);
      }
    };

    fetchData();
  }, []);

  const handleLoadData = () => {
    if (rosBagFile === "") {
      setOpen(true);
    } else {
      navigate("/main/" + rosBagFile + "/" + bookListFile);
    }
  };

  const handleClose = (event?: React.SyntheticEvent, reason?: string) => {
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
                  <ListItemText primary={fileName} />
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
            Predefined Booklist
          </Typography>
          <List component="nav" aria-label="Predefined Booklist">
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
                  <ListItemText primary={fileName} />
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
            {/* {fileNameList.annotation_files.map((fileName, index) => (
              <ListItem
                button
                key={index}
                onClick={() => {
                  setAnnotationFile(fileName);
                  setAnnotSelectedIndex(index);
                }}
                selected={annotSelectedIndex === index}
              >
                <ListItemText primary={fileName} />
              </ListItem>
            ))} */}
            <ListItem button>
              <ListItemText primary="Not Supported for Now" />
            </ListItem>
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

      <Snackbar
        anchorOrigin={{ vertical: "top", horizontal: "center" }}
        open={open}
        autoHideDuration={6000}
        onClose={handleClose}
        message="ROSBag Data File cannot be empty!"
      />
    </div>
  );
}

export default LoadableList;
