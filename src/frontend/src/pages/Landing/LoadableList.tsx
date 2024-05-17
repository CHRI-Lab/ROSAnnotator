import {
  List,
  ListItem,
  ListItemText,
  Paper,
  Typography,
  Button,
} from "@mui/material";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

const fileNameListTest = {
  rosBagList: ["rosbag1", "rosbag2", "rosbag3"],
  bookList: ["book1", "book2", "book3"],
  annotationList: ["annotation1", "annotation2", "annotation3"],
};

function LoadableList() {
  const [fileNameList, setFileNameList] = useState(fileNameListTest);
  const [rosBagFile, setRosBagFile] = useState("");
  const [bookListFile, setBookListFile] = useState("");
  const [annotationFile, setAnnotationFile] = useState("");

  const navigate = useNavigate();

  useEffect(() => {
    // fetch("/api/getFileList")
    //   .then((response) => response.json())
    //   .then((data) => {
    //     setFileNameList(data);
    //   });
  }, []);

  const handleLoadData = () => {
    navigate("/main/" + rosBagFile + "+" + bookListFile + "+" + annotationFile);
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
            {/* <ListItem button>
              <ListItemText primary="Item 1" />
            </ListItem>
            <ListItem button>
              <ListItemText primary="Item 2" />
            </ListItem> */}
            {fileNameList.rosBagList.map((fileName, index) => (
              <ListItem
                button
                key={index}
                onClick={() => setRosBagFile(fileName)}
              >
                <ListItemText primary={fileName} />
              </ListItem>
            ))}
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
            {fileNameList.bookList.map((fileName, index) => (
              <ListItem
                button
                key={index}
                onClick={() => setBookListFile(fileName)}
              >
                <ListItemText primary={fileName} />
              </ListItem>
            ))}
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
            {fileNameList.annotationList.map((fileName, index) => (
              <ListItem
                button
                key={index}
                onClick={() => setAnnotationFile(fileName)}
              >
                <ListItemText primary={fileName} />
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
    </div>
  );
}

export default LoadableList;
