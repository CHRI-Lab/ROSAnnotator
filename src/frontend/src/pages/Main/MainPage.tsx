import React, { useEffect, useState } from "react";
import LoadingPage from "../Loading";
import Annotator from "../Annotator";
import { useParams } from "react-router-dom";
import { Paper } from "@mui/material";
// import axios from "axios";

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
      <Paper elevation={3}>
        <h1>Error</h1>
        <p>Error loading your files, Please try again.</p>
        <p>Error: {String(error)}</p>
      </Paper>
    );
  }

  return (
    <div>
      <Annotator />
    </div>
  );
};

export default MainPage;
