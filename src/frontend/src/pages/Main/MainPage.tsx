import { useCallback, useEffect, useRef, useState } from "react";
import LoadingPage from "../Loading";
import Annotator from "../Annotator";
import { useParams, useSearchParams } from "react-router-dom";

import { Box, Dialog, DialogTitle, DialogActions, DialogContent, Typography, Button } from "@mui/material";
import { alpha } from "@mui/material/styles";
import {
  ChunkManifest,
  getChunkManifest,
} from "../../api/chunks";

import {
  loadDataViews,
  type AnnotationSourceCheck,
  type ViewPayload,
} from "../../api/dataViews";
import type { AxisData, BookList } from "../../types/annotations";

import { stripExtension, formatSeconds } from "../../components/Timeline/saveUtils";

type ChunkPageData = ViewPayload;

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

// A file with no recorded source loads silently: every annotation file written
// before this feature has none, and prompting on all of them would train people
// to dismiss the dialogue without reading it. Overhang is asked about whatever
// the provenance, because blocks are lost either way.
const needsSourceConfirmation = (
  check?: AnnotationSourceCheck | null,
): check is AnnotationSourceCheck =>
  Boolean(check && (check.status === "mismatch" || check.overflows));

const MainPage = () => {
  const { rosBagFile, bookListFile, annotationFile } = useParams();
  const [searchParams] = useSearchParams();
  const manifestId = searchParams.get("manifestId");
  const [loading, setLoading] = useState(true);
  const [switchingChunk, setSwitchingChunk] = useState(false);
  const [data, setData] = useState<ChunkPageData | null>(null);
  const [bookListData, setBookListData] = useState<BookList>({});
  const [chunkManifest, setChunkManifest] = useState<ChunkManifest | null>(null);
  const [currentChunkIndex, setCurrentChunkIndex] = useState(0);
  const shouldRestore = searchParams.get("restore") === "autosave";
  const [restoredAxes, setRestoredAxes] = useState<AxisData[] | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [errorDisplay, setErrorDisplay] = useState(false);
  const [pendingRecovery, setPendingRecovery] = useState<PendingRecovery | null>(null);
  const [pendingSourceCheck, setPendingSourceCheck] =                    
    useState<AnnotationSourceCheck | null>(null);                        
    // Survives chunk switches, unlike anything held in Annotator or Timeline.
  const [savedAnnotationName, setSavedAnnotationName] = useState("");
  const requestGeneration = useRef(0);
  const chunkChangeInProgress = useRef(false);
  const sourceCheckAsked = useRef(false);            // Asked at most once per load.                     
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
    setPendingSourceCheck(null);      
    sourceCheckAsked.current = false;
    setSavedAnnotationName(annotationFile ? stripExtension(annotationFile) : "");

    const fetchData = async () => {
      try {
        if (!rosBagFile) throw new Error("A ROSBag file must be selected.");
        let manifest: ChunkManifest | null = null;
        let recoveredAxes: AxisData[] | null = null;
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
          if (!sourceCheckAsked.current                                  
              && needsSourceConfirmation(payload.annotation_source_check)) {
            sourceCheckAsked.current = true;
            setPendingSourceCheck(payload.annotation_source_check);
          }
          setData(payload);
          setBookListData(payload.booklist_data);
          setLoading(false);
        };
        const loadedData = await loadDataViews(
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
        if (!sourceCheckAsked.current                                    
            && needsSourceConfirmation(loadedData.annotation_source_check)) {
          sourceCheckAsked.current = true;
          setPendingSourceCheck(loadedData.annotation_source_check);
        }
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
      requestGeneration.current = generation + 1;
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

  const sourceCheckPrompt = (() => {
    const check = pendingSourceCheck;
    if (!check) return null;

    // "loss" marks a line describing annotations that will not survive the
    // load. Those get a tint; identification details do not, so the weight on
    // the page matches the weight of the consequence.
    const lines: { text: string; severity: "info" | "loss" }[] = [];

    if (check.status === "mismatch") {
      if (check.name_differs && check.recorded_bag_filename) {
        lines.push({
          severity: "info",
          text: `This annotation file records that it was made against "${check.recorded_bag_filename}", but you are loading "${check.loaded_bag_filename}".`,
        });
      }
      if (check.duration_differs) {
        lines.push({
          severity: "info",
          text: check.name_differs
            ? `They are also different lengths: the recorded one is ${formatSeconds(check.recorded_duration ?? undefined)}, this one is ${formatSeconds(check.loaded_duration ?? undefined)}.`
            : `This annotation file records a recording ${formatSeconds(check.recorded_duration ?? undefined)} long, but "${check.loaded_bag_filename}" is ${formatSeconds(check.loaded_duration ?? undefined)} long. It may be a different recording saved under the same name.`,
        });
      }
    }

    if (check.overflows) {
      const trimmed = check.overflow_block_count;
      const dropped = check.orphan_block_count;
      const effects: string[] = [];
      if (dropped) {
        effects.push(
          `${dropped} ${dropped === 1 ? "annotation falls" : "annotations fall"} entirely outside it and will be discarded`
        );
      }
      if (trimmed) {
        effects.push(
          `${trimmed} ${trimmed === 1 ? "annotation extends" : "annotations extend"} past the end and will be trimmed to it`
        );
      }
      lines.push({
        // The only line describing annotations that do not survive.
        severity: dropped ? "loss" : "info",
        text: `The annotations run to ${formatSeconds(check.annotation_end_seconds)}, past the end of this recording at ${formatSeconds(check.loaded_duration ?? undefined)}. ${effects.join(", and ")}.`,
      });
    }

    return {
      title:
        check.status === "mismatch"
          ? "This annotation file may not belong to this recording"
          : "Some annotations fall outside this recording",
      lines,
    };
  })();

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
      <Dialog open={pendingSourceCheck !== null} disableEscapeKeyDown>
        <DialogTitle>{sourceCheckPrompt?.title}</DialogTitle>
        <DialogContent>
          {sourceCheckPrompt?.lines.map((line, index) =>
            line.severity === "loss" ? (
              <Box
                key={index}
                sx={(theme) => ({
                  mt: index ? 2 : 0,
                  px: 2,
                  py: 1.5,
                  borderRadius: 1,
                  bgcolor: alpha(theme.palette.error.main, 0.12),
                  borderLeft: `3px solid ${theme.palette.error.main}`,
                })}
              >
                <Typography>{line.text}</Typography>
              </Box>
            ) : (
              <Typography key={index} sx={{ mt: index ? 2 : 0 }}>
                {line.text}
              </Typography>
            )
          )}
          <Typography sx={{ mt: 2 }} color="text.secondary">
            Nothing is written until you save, so the file on disk is unchanged
            either way.
          </Typography>
        </DialogContent>
        <DialogActions>
          <Button href="/" color="error">
            Back to file selection
          </Button>
          <Button onClick={() => setPendingSourceCheck(null)} variant="contained">
            Load anyway
          </Button>
        </DialogActions>
      </Dialog>

      <Dialog
        open={pendingSourceCheck === null && pendingRecovery !== null}  
        disableEscapeKeyDown
      >
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
        autosaveEnabled={pendingRecovery === null && pendingSourceCheck === null}
        onAutosaveReady={registerAutosave}
        savedAnnotationName={savedAnnotationName}
        onAnnotationSaved={setSavedAnnotationName}
      />}
    </div>
  );
};

export default MainPage;
