import { useEffect, useState } from "react";
import LoadingPage from "../Loading";
import Annotator from "../Annotator";
import { useParams, useSearchParams } from "react-router-dom";

import { Dialog, DialogTitle, DialogContent, Typography } from "@mui/material";
import {
  ChunkManifest,
  getChunkManifest,
  processChunk,
} from "../../api/chunks";

interface ChunkPageData {
  video_path: string;
  audio_transcript: string;
  booklist_data: unknown;
  annotation_data: unknown;
  speaker_data?: Array<unknown>;
  [key: string]: unknown;
}

const MainPage = () => {
  const { rosBagFile, bookListFile, annotationFile } = useParams();
  const [searchParams] = useSearchParams();
  const manifestId = searchParams.get("manifestId");
  const [loading, setLoading] = useState(true);
  const [switchingChunk, setSwitchingChunk] = useState(false);
  const [data, setData] = useState<ChunkPageData | null>(null);
  const [bookListData, setBookListData] = useState<unknown>(null);
  const [chunkManifest, setChunkManifest] = useState<ChunkManifest | null>(null);
  const [currentChunkIndex, setCurrentChunkIndex] = useState(0);
  const [error, setError] = useState<unknown>(null);
  const [errorDisplay, setErrorDisplay] = useState(false);

  useEffect(() => {
    console.log(rosBagFile, bookListFile, annotationFile);
    // Define the async function to fetch data
    const fetchData = async () => {
      try {
        if (manifestId) {
          const manifest = await getChunkManifest(manifestId);
          const firstChunk = await processChunk(manifestId, 0);
          setChunkManifest(manifest);
          setCurrentChunkIndex(0);
          setData(firstChunk);
          setBookListData(firstChunk.booklist_data);
          setLoading(false);
          return;
        }
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
  }, [annotationFile, bookListFile, manifestId, rosBagFile]);

  const handleChunkChange = async (targetIndex: number) => {
    if (!manifestId || targetIndex === currentChunkIndex || switchingChunk) return;
    setSwitchingChunk(true);
    try {
      // Auto-save integration point: await the autosave flush here before load.
      const nextChunk = await processChunk(manifestId, targetIndex);
      const refreshedManifest = await getChunkManifest(manifestId);
      setData(nextChunk);
      setBookListData(nextChunk.booklist_data);
      setChunkManifest(refreshedManifest);
      setCurrentChunkIndex(targetIndex);
    } catch (error) {
      setError(error);
      setErrorDisplay(true);
    } finally {
      setSwitchingChunk(false);
    }
  };

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
        key={manifestId ? `${manifestId}-chunk-${currentChunkIndex}` : "whole-input"}
        rosBagFileName={rosBagFile}
        bookListFileName={bookListFile}
        data={data}
        bookListData={bookListData}
        chunkManifest={chunkManifest}
        currentChunkIndex={currentChunkIndex}
        switchingChunk={switchingChunk}
        onChunkChange={handleChunkChange}
      />
    </div>
  );
};

export default MainPage;
