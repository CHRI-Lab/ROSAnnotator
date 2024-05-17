import React, { useEffect, useState } from "react";
import LoadingPage from "../Loading";
import Annotator from "../Annotator";
// import axios from "axios";

const MainPage = () => {
  const [loading, setLoading] = useState(true);
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    // Define the async function to fetch data
    const fetchData = async () => {
      //   try {
      //     const response = await axios.get("https://api.example.com/data");
      //     setData(response.data);
      //     setLoading(false); // Set loading to false after data is fetched
      //   } catch (error) {
      //     setError(error);
      //     setLoading(false); // Set loading to false even if there's an error
      //   }
    };

    fetchData();
  }, []); // Empty dependency array means this effect runs once after the initial render

  if (loading) {
    return <LoadingPage />;
  }

  if (error) {
    // return <div>Error: {error.message}</div>;
  }

  return (
    <div>
      <Annotator />
    </div>
  );
};

export default MainPage;
