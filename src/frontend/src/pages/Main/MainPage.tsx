import { useEffect, useRef, useState } from "react";
import LoadingPage from "../Loading";
import Annotator from "../Annotator";
import { useParams, useSearchParams } from "react-router-dom";

import { Dialog, DialogTitle, DialogContent, Typography, Button } from "@mui/material";
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
}

import {
  fetchAutosave,
  hydrateAutosaveAxes,
} from "../../components/Autosave/autosaveUtils";

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
  const shouldRestore = searchParams.get("restore") === "autosave";
  const [restoredAxes, setRestoredAxes] = useState<any[] | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [errorDisplay, setErrorDisplay] = useState(false);
  const requestGeneration = useRef(0);
  const chunkChangeInProgress = useRef(false);

  useEffect(() => {
    const generation = ++requestGeneration.current;
    let cancelled = false;
    const isCurrent = () => !cancelled && generation === requestGeneration.current;
    chunkChangeInProgress.current = false;
    setLoading(true);
    setSwitchingChunk(false);
    setError(null);
    setErrorDisplay(false);
    setData(null);
    setChunkManifest(null);
    setCurrentChunkIndex(0);
    setRestoredAxes(null);

    const fetchData = async () => {
      try {
        if (!rosBagFile) throw new Error("A ROSBag file must be selected.");
        let loadedData: ChunkPageData;
        let manifest: ChunkManifest | null = null;
        let recoveredAxes: any[] | null = null;

        if (manifestId) {
          manifest = await getChunkManifest(manifestId);
          if (!isCurrent()) return;
          if (manifest.bag_filename !== rosBagFile) {
            throw new Error("The chunk manifest belongs to a different ROSBag.");
          }
          if (shouldRestore && manifest.chunking_enabled) {
            throw new Error("Whole-input recovery cannot be applied to a split chunk. Restore from the file selection page.");
          }
          loadedData = await processChunk(manifestId, 0);
        } else {
          const response = await fetch("http://localhost:8000/api/process_rosbag/", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              bag_filename: rosBagFile,
              booklist_filename: bookListFile,
              annotation_filename: annotationFile,
            }),
          });
          const payload = await response.json();
          if (!response.ok) throw new Error(payload.error || "Error loading the ROSBag.");
          loadedData = payload;
        }
        if (!isCurrent()) return;

        // Restore before mounting Timeline, including whole-input manifests.
        // If recovery fails, keep the editor closed so edits cannot overwrite it.
        if (shouldRestore) {
          const payload = await fetchAutosave(rosBagFile);
          if (payload.bag_filename !== rosBagFile || !Array.isArray(payload.axes)) {
            throw new Error("The autosave does not contain valid data for this ROSBag.");
          }
          recoveredAxes = hydrateAutosaveAxes(payload.axes);
        }
        if (!isCurrent()) return;
        setChunkManifest(manifest);
        setRestoredAxes(recoveredAxes);
        setData(loadedData);
        setBookListData(loadedData.booklist_data);
      } catch (error) {
        if (!isCurrent()) return;
        setError(error);
        setErrorDisplay(true);
      } finally {
        if (isCurrent()) setLoading(false);
      }
    };

    void fetchData();
    return () => {
      cancelled = true;
      requestGeneration.current++;
    };
  }, [annotationFile, bookListFile, manifestId, rosBagFile, shouldRestore]);

  const handleChunkChange = async (targetIndex: number) => {
    if (
      !manifestId || chunkChangeInProgress.current || loading ||
      targetIndex === currentChunkIndex ||
      !chunkManifest?.chunks.some((chunk) => chunk.index === targetIndex)
    ) return;
    const generation = requestGeneration.current;
    chunkChangeInProgress.current = true;
    setSwitchingChunk(true);
    setError(null);
    setErrorDisplay(false);
    try {
      const nextChunk = await processChunk(manifestId, targetIndex);
      if (generation !== requestGeneration.current) return;
      const refreshedManifest = await getChunkManifest(manifestId);
      if (generation !== requestGeneration.current) return;
      setData(nextChunk);
      setBookListData(nextChunk.booklist_data);
      setChunkManifest(refreshedManifest);
      setRestoredAxes(null);
      setCurrentChunkIndex(targetIndex);
    } catch (error) {
      if (generation !== requestGeneration.current) return;
      // Keep the current editor mounted when switching fails.
      setError(error);
      setErrorDisplay(true);
    } finally {
      if (generation === requestGeneration.current) {
        chunkChangeInProgress.current = false;
        setSwitchingChunk(false);
      }
    }
  };

  if (loading) {
    return <LoadingPage />;
  }


  return (
    <div>
      <Dialog open={errorDisplay} onClose={() => data && setErrorDisplay(false)}>
        <DialogTitle>Error loading your files</DialogTitle>
        <DialogContent>
          <Typography color="error">{String(error)}</Typography>
          {data && <Button onClick={() => setErrorDisplay(false)}>Back to current chunk</Button>}
          {!data && <Button href="/">Back to file selection</Button>}
        </DialogContent>
      </Dialog>
      {data && <Annotator
        key={manifestId ? `${manifestId}-chunk-${currentChunkIndex}` : "whole-input"}
        rosBagFileName={rosBagFile}
        bookListFileName={bookListFile}
        data={data}
        bookListData={bookListData}
        chunkManifest={chunkManifest}
        currentChunkIndex={currentChunkIndex}
        switchingChunk={switchingChunk}
        onChunkChange={handleChunkChange}
        restoredAxes={restoredAxes}
        autosaveEnabled={!chunkManifest?.chunking_enabled}
      />}
    </div>
  );
};

export default MainPage;
