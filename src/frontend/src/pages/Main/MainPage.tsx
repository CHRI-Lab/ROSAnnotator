import { useCallback, useEffect, useRef, useState } from "react";
import LoadingPage from "../Loading";
import Annotator from "../Annotator";
import { useParams, useSearchParams } from "react-router-dom";

import { Dialog, DialogTitle, DialogActions, DialogContent, Typography, Button } from "@mui/material";
import {
  ChunkManifest,
  getChunkManifest,
} from "../../api/chunks";

import type { BackendDataView } from "../../components/FrontEndWorkspace/viewTypes";

import { loadDataViews, ViewPayload } from "../../api/dataViews";

interface ChunkPageData {
  views?: Record<string, BackendDataView>;
  duration_seconds?: number;
  video_path: string;
  audio_transcript: string;
  booklist_data: unknown;
  annotation_data: unknown;
  speaker_data?: Array<unknown>;
}

import {
  AutosaveMeta,
  AutosaveScope,
  deleteAutosave,
  fetchAutosave,
  fetchAutosaveMeta,
  formatAutosaveTimestamp,
  hydrateAutosaveAxes,
} from "../../components/Autosave/autosaveUtils";

type PendingRecovery = { scope: AutosaveScope; meta: AutosaveMeta };

// Metadata only. Never applies anything.
const checkChunkRecovery = async (
  bag: string, id: string, index: number,
): Promise<PendingRecovery | null> => {
  const scope = { manifest_id: id, chunk_index: index };
  const meta = await fetchAutosaveMeta(bag, scope).catch(
    () => ({ exists: false }) as AutosaveMeta,
  );
  return meta.exists ? { scope, meta } : null;
};

// Called only after the user chooses to restore.
const loadChunkRecovery = async (bag: string, scope: AutosaveScope) => {
  const payload = await fetchAutosave(bag, scope);
  if (
    payload.bag_filename !== bag ||
    payload.manifest_id !== scope.manifest_id ||
    payload.chunk_index !== scope.chunk_index ||
    !Array.isArray(payload.axes)
  ) {
    throw new Error("The autosave does not belong to this chunk.");
  }
  return hydrateAutosaveAxes(payload.axes);
};

const requireAvailableViews = (data: ChunkPageData) => {
  if (data.views && !Object.values(data.views).some(view => view.available && view.status === 'ready' && view.processed_data != null)) {
    throw new Error('No usable data views are available. ' + Object.values(data.views)
      .map(view => `${view.view_id}: ${view.reason || 'Unavailable'}`).join(' '));
  }
};

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
  const [pendingRecovery, setPendingRecovery] = useState<PendingRecovery | null>(null);
  const requestGeneration = useRef(0);
  const chunkChangeInProgress = useRef(false);
  const autosaveFlush = useRef<(() => Promise<void>) | null>(null);
  const registerAutosave = useCallback((flush: (() => Promise<void>) | null) => {
    autosaveFlush.current = flush;
  }, []);

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
    setPendingRecovery(null);

    const fetchData = async () => {
      try {
        if (!rosBagFile) throw new Error("A ROSBag file must be selected.");
        let loadedData: ChunkPageData;
        let manifest: ChunkManifest | null = null;
        let recoveredAxes: any[] | null = null;
        let pending: PendingRecovery | null = null;

        if (manifestId) {
          manifest = await getChunkManifest(manifestId);
          if (!isCurrent()) return;
          if (manifest.bag_filename !== rosBagFile) throw new Error('The chunk manifest belongs to a different ROSBag.');
          if (shouldRestore && manifest.chunking_enabled) throw new Error('Whole-input recovery cannot be applied to a split chunk.');
          if (manifest.chunking_enabled) pending = await checkChunkRecovery(rosBagFile, manifestId, 0);
        }
        if (shouldRestore) {
          const payload = await fetchAutosave(rosBagFile);
          if (payload.bag_filename !== rosBagFile || !Array.isArray(payload.axes)) {
            throw new Error('The autosave does not contain valid data for this ROSBag.');
          }
          recoveredAxes = hydrateAutosaveAxes(payload.axes);
        }
        const showProgress = (payload: ViewPayload) => {
          if (!isCurrent() || !Object.values(payload.views).some(view => view.available)) return;
          setChunkManifest(manifest);
          setRestoredAxes(recoveredAxes);
          setPendingRecovery(pending);
          setData(payload);
          setBookListData(payload.booklist_data);
          setLoading(false);
        };
        loadedData = await loadDataViews(
          manifestId ? `http://localhost:8000/api/chunks/${manifestId}/0/process/`
            : 'http://localhost:8000/api/process_rosbag/',
          { bag_filename: rosBagFile, booklist_filename: bookListFile, annotation_filename: annotationFile },
          showProgress,
        );
        requireAvailableViews(loadedData);
        if (!isCurrent()) return;
        setChunkManifest(manifest);
        setRestoredAxes(recoveredAxes);
        setPendingRecovery(pending);
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
      if (!autosaveFlush.current) throw new Error("The editor is not ready to save. Please retry.");
      await autosaveFlush.current();
      if (generation !== requestGeneration.current) return;
      const nextChunk = await loadDataViews(
        `http://localhost:8000/api/chunks/${manifestId}/${targetIndex}/process/`, {},
      );
      requireAvailableViews(nextChunk);
      if (generation !== requestGeneration.current) return;
      const refreshedManifest = await getChunkManifest(manifestId);
      if (generation !== requestGeneration.current) return;
      const pending = await checkChunkRecovery(rosBagFile!, manifestId, targetIndex);
      if (generation !== requestGeneration.current) return;
      setData(nextChunk);
      setBookListData(nextChunk.booklist_data);
      setChunkManifest(refreshedManifest);
      setRestoredAxes(null);
      setPendingRecovery(pending);
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

    const handleRestorePending = async () => {
    if (!pendingRecovery || !rosBagFile) return;
    const { scope } = pendingRecovery;
    setPendingRecovery(null);
    try {
      setRestoredAxes(await loadChunkRecovery(rosBagFile, scope));
    } catch (error) {
      setError(error);
      setErrorDisplay(true);
    }
  };

  const handleDiscardPending = async () => {
    if (!pendingRecovery || !rosBagFile) return;
    const { scope } = pendingRecovery;
    setPendingRecovery(null);
    setRestoredAxes(null);
    try {
      await deleteAutosave(rosBagFile, scope);
    } catch (error) {
      // A surviving recovery file is a smaller problem than blocking the user.
      console.warn("[autosave] Could not delete the autosave.", error);
    }
  };

  if (loading) {
    return <LoadingPage />;
  }


  return (
    <div>
      <Dialog open={switchingChunk}>
        <DialogTitle>Autosaving and switching chunk…</DialogTitle>
      </Dialog>
      <Dialog open={errorDisplay} onClose={() => data && setErrorDisplay(false)}>
        <DialogTitle>{data ? "Unable to switch chunk" : "Error loading your files"}</DialogTitle>
        <DialogContent>
          <Typography color="error">{String(error)}</Typography>
          {data && <Button onClick={() => setErrorDisplay(false)}>Back to current chunk</Button>}
          {!data && <Button href="/">Back to file selection</Button>}
        </DialogContent>
      </Dialog>
      <Dialog open={pendingRecovery !== null} disableEscapeKeyDown>
        <DialogTitle>Unsaved work found in this chunk</DialogTitle>
        <DialogContent>
          <Typography>
            {`Chunk ${(pendingRecovery?.scope.chunk_index ?? 0)+1} has unsaved work from ${
              formatAutosaveTimestamp(pendingRecovery?.meta.saved_at)
            }, with ${pendingRecovery?.meta.axis_count ?? 0} time ${
              pendingRecovery?.meta.axis_count === 1 ? "axis" : "axes"
            } and ${pendingRecovery?.meta.block_count ?? 0} annotations.`}
          </Typography>
          {pendingRecovery?.meta.recovered_from_backup && (
            <Typography sx={{ mt: 2 }}>
              The most recent copy could not be read, so this is the previous
              one. Some recent edits may be missing.
            </Typography>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={handleDiscardPending} color="error">
            Discard and start fresh
          </Button>
          <Button onClick={handleRestorePending} variant="contained">
            Restore work
          </Button>
        </DialogActions>
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
        autosaveEnabled={pendingRecovery === null}
        onAutosaveReady={registerAutosave}
      />}
    </div>
  );
};

export default MainPage;
