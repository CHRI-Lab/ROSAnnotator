import React, { useEffect, useState } from "react";
import LoadingPage from "../Loading";
import Annotator from "../Annotator";
import { useParams } from "react-router-dom";

import { Dialog, DialogTitle, DialogContent, Typography } from "@mui/material";

const MainPage = () => {
  const { rosBagFile, bookListFile, annotationFile } = useParams();
  const [loading, setLoading] = useState(true);
  const [data, setData] = useState(null);
  const [bookListData, setBookListData] = useState(null);
  const [error, setError] = useState<unknown>(null);
  const [errorDisplay, setErrorDisplay] = useState(false);

  useEffect(() => {
    console.log(rosBagFile, bookListFile, annotationFile);
    // Define the async function to fetch data
    const fetchData = async () => {
      try {
        const response = await fetch(
          "http://localhost:8000/api/process_rosbag/",
          {
            method: "POST",
            headers: {
              "Content-Type": "application/json",
            },
            body: JSON.stringify({
              bag_filename: rosBagFile,
              booklist_filename: bookListFile,
              annotation_filename: annotationFile,
            }),
          }
        );

        const data = await response.json();

        if (!response.ok) {
          switch (response.status) {
            case 500:
              throw new Error(data.error);
            case 400:
              throw new Error(data.error);
            case 405:
              throw new Error("Method not allowed");
            default:
              throw new Error("Error resolving request");
          }
        }

        setData(data);
        setBookListData(data.booklist_data);
        setLoading(false);
      } catch (error) {
        setError(error);
        setErrorDisplay(true);
        setLoading(false);
      }
    };

    fetchData();
  }, []);

  if (loading) {
    return <LoadingPage />;
  }

  if (error) {
    return (
      <Dialog open={errorDisplay}>
        <DialogTitle>
          <Typography variant="h6" color="error">
            Error
          </Typography>
        </DialogTitle>
        <DialogContent>
          <Typography variant="body1">
            Error loading your files, Please try again.
          </Typography>
          <br />
          <Typography variant="body2" color="error">
            Message: {String(error)}
          </Typography>
        </DialogContent>
      </Dialog>
    );
  }

  return (
    <div>
      <Annotator
        rosBagFileName={rosBagFile}
        bookListFileName={bookListFile}
        data={data}
        bookListData={bookListData}
      />
    </div>
  );
};

export default MainPage;
