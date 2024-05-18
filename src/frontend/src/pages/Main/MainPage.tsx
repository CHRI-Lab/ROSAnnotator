import React, { useEffect, useState } from "react";
import LoadingPage from "../Loading";
import Annotator from "../Annotator";
import { useParams } from "react-router-dom";

import { Dialog, DialogTitle, DialogContent, Typography } from "@mui/material";

const MainPage = () => {
  const { rosBagFile, bookListFile } = useParams();
  const [loading, setLoading] = useState(true);
  const [data, setData] = useState(null);
  const [error, setError] = useState<unknown>(null);

  useEffect(() => {
    // Define the async function to fetch data
    const fetchData = async () => {
      try {
        const response = await fetch(`/api/${rosBagFile}/${bookListFile}`);
        const data = await response.json();
        setData(data);
        setLoading(false);
      } catch (error) {
        setError(error);
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
      <Dialog open={true}>
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
            Error Message: {String(error)}
          </Typography>
        </DialogContent>
      </Dialog>
    );
  }

  return (
    <div>
      <Annotator />
    </div>
  );
};

export default MainPage;
