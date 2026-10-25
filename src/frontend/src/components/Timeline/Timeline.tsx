import React, { useCallback, useState, useEffect, useContext, useRef } from "react";
import { DragDropContext, DropResult } from 'react-beautiful-dnd';
import {
  Alert,
  Button,
  Slider,
  Paper,
  Dialog,
  DialogTitle,
  DialogActions,
  DialogContent,
  DialogContentText,
  TextField,
  Tooltip,
} from "@mui/material";
import { styled } from "@mui/system";
import Axis from "../Axis";
import AxisManager from "../AxisManager";
import AxesContext from "../AxesProvider";
import {
  buildDefaultAnnotationName,
  isValidAnnotationName,
  collectAnnotationData,
  postAnnotation,
  AnnotationSaveConflict,
  formatSeconds
} from "./saveUtils";
import useAutosave from "../Autosave/useAutosave";
import {
  highestAxisId,
  deleteAutosave,
  AutosaveScope,
  formatAutosaveTimestamp,
} from "../Autosave/autosaveUtils";
import { AIInstruction, AIRecord } from "../../types/aiRecords";
import type {
  AnnotationAxisPayload,
  AxisData,
  BookList,
  SpeakerSegment,
} from "../../types/annotations";
import { applyAIInstruction, isDuplicateAxisName } from "./aiInstruction";
import { convertTranscriptToAnnotations } from "./transcriptAnnotations";
import { clampAxesToDuration, clampBlockToDuration } from "./blockBounds";

let globalAxisId = 1;

interface TimelineProps {
  duration: number;
  sourceDuration?: number;
  chunkCount?: number;
  rosBagFileName: string;
  bookListFileName: string;
  booklist: BookList;
  annotationData: AnnotationAxisPayload[] | null;
  speakerData?: SpeakerSegment[];
  restoredAxes?: AxisData[] | null;
  carriedAxes?: AxisData[] | null;
  autosaveEnabled?: boolean;
  autosaveScope?: AutosaveScope;
  onAutosaveReady?: (flush: (() => Promise<void>) | null) => void;
  switchingChunk?: boolean;
  onAxesUpdate: (axes: AxisData[]) => void;
  instruction: AIInstruction | null;
  aiRecords: AIRecord[];
  onSaveReady?: (openSaveDialog: (() => void) | null) => void;
  savedAnnotationName?: string;
  onAnnotationSaved?: (name: string) => void;
}

type PendingDeletion =
  | { kind: "block"; axisId: number; blockIndex: number }
  | { kind: "axis"; axisId: number };

const MainContainer = styled(Paper)(({ theme }) => ({
  display: "flex",
  flexDirection: "column",
  alignItems: "center",
  background: theme.palette.background.paper,
  boxShadow: "0px 1px 5px rgba(0,0,0,0.2)",
  padding: "20px",
  margin: "20px",
  width: "auto",
}));

const ControlsContainer = styled("div")({
  display: "flex",
  flexWrap: "wrap",
  gap: "12px",
  justifyContent: "space-between",
  alignItems: "center",
  marginBottom: "8px",
  width: "100%",
});

const ScrollableTimelineContainer = styled("div")({
  overflowX: "scroll",
  overflowY: "hidden",
  width: "100%",
  padding: "0 0 10px",
  position: "relative",
});

const TimelineGrid = styled("div")({
  display: "grid",
  gridTemplateColumns: "170px minmax(0, 1fr)",
  alignItems: "stretch",
});

const TimelineControlCell = styled("div")(({ theme }) => ({
  position: "sticky",
  left: 0,
  zIndex: 2,
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  width: "170px",
  boxSizing: "border-box",
  padding: "0 10px",
  backgroundColor: theme.palette.background.paper,
}));

const DurationLabel = styled(TimelineControlCell)(({ theme }) => ({
  color: theme.palette.text.primary,
  fontSize: "0.875rem",
  fontWeight: 600,
  textAlign: "center",
}));

const AxisControlCell = styled(TimelineControlCell)({
  // Axis has a 10px top margin. Matching that space here centres the button
  // on the visible axis box instead of the entire grid row.
  paddingTop: "10px",
});

const DurationTimelineCell = styled("div")({
  height: "60px",
  padding: "15px 10px",
  boxSizing: "border-box",
});

const TimelineMarksCell = styled("div")({
  padding: "0 10px",
  boxSizing: "border-box",
});

const TimelineMarks = styled("div")({
  position: "relative",
  display: "flex",
  alignItems: "center",
  height: "10px",
});

const TimelineMarkLabel = styled("div")(({ theme }) => ({
  position: "absolute",
  color: theme.palette.text.primary,
  fontSize: "0.75rem",
  transform: "translateX(-50%)",
  userSelect: "none",
}));

const Timeline: React.FC<TimelineProps> = ({
  duration,
  sourceDuration,
  chunkCount = 1,
  rosBagFileName,
  bookListFileName,
  booklist,
  annotationData,
  speakerData,
  onAxesUpdate,
  instruction,
  restoredAxes,
  carriedAxes,
  autosaveEnabled = true,
  autosaveScope,
  onAutosaveReady,
  onSaveReady,
  switchingChunk = false,
  savedAnnotationName,
  onAnnotationSaved
}) => {
  const [markInterval] = useState(1);
  const [selectedRange, setSelectedRange] = useState<number[]>([
    0,
    0.1 * duration,
  ]);
  const [isDialogOpen, setIsDialogOpen] = useState(false);
  const [error, setError] = useState("");
  const [isErrorDialogOpen, setIsErrorDialogOpen] = useState(false);
  const [transcriptConversionNotice, setTranscriptConversionNotice] = useState<string | null>(null);
  const [pendingDeletion, setPendingDeletion] =
    useState<PendingDeletion | null>(null);
  const lastExecutedInstruction = useRef<AIInstruction | null>(null);

  const { axes, setAxes } = useContext(AxesContext)!;

  // SAVE FUNCTIONALITY
  const [isSaveDialogOpen, setIsSaveDialogOpen] = useState(false); // flag controlling whether the "name your annotation" popup is currently visible
  const [annotationName, setAnnotationName] = useState(""); //container for annotation name text
  // Holds a save the backend refused because the file already exists, until
  // the user either confirms the replacement or picks another name.
  const [pendingOverwrite, setPendingOverwrite] = useState<{
    name: string;
    data: AnnotationAxisPayload[];
    conflict: AnnotationSaveConflict;
  } | null>(null);
  const [hasUnsavedEdits, setHasUnsavedEdits] = useState(false);
  

  const autosave = useAutosave({
    enabled: autosaveEnabled && Boolean(rosBagFileName),
    bagFileName: rosBagFileName,
    scope: autosaveScope,
    axes,
    hasUnsavedEdits,
    bookListFileName,
    annotationName,
    onAutosaved: (savedAt) => {
      const blockCount = axes.reduce(
        (total, axis) => total + (axis.blocks?.length ?? 0),
        0
      );
      console.log(
        `[autosave] ${savedAt} — ${axes.length} axes, ${blockCount} blocks`
      );
    },
  });
  const isLoadingData = useRef(true); //initialize true upon load
  const { markSynced } = autosave;
  const { flush } = autosave;
  useEffect(() => {
    onAutosaveReady?.(flush);
    return () => onAutosaveReady?.(null);
  }, [flush, onAutosaveReady]);

  useEffect(() => {
    if (restoredAxes) {
      markSynced(restoredAxes);
    } else if (carriedAxes) {
      markSynced(carriedAxes);
    }
  }, [restoredAxes, carriedAxes, markSynced]);

  useEffect(() => {
    if (instruction && lastExecutedInstruction.current !== instruction) {
      lastExecutedInstruction.current = instruction;
      setAxes((currentAxes) => applyAIInstruction(currentAxes, instruction, duration));
    }
  }, [instruction, setAxes, duration]);

  useEffect(() => {
    if (onAxesUpdate) {
      onAxesUpdate(axes);
    }
  }, [axes, onAxesUpdate]);

  useEffect(() => {
    console.log("booklist passed to Timeline:", booklist);
  }, [booklist]);


  useEffect(() => { // marks when unsaved changes are detected
    // Skip flagging unsaved edits on the first render / data load
    if (isLoadingData.current) {
      isLoadingData.current = false; // consume the flag, reset for next time
      setHasUnsavedEdits(false); // a fresh load is always "in sync," regardless of prior state
      console.log("Data loaded. No unsaved edits.");
      return;
    }
    console.log(" Annotations modified. You have unsaved changes.");
    setHasUnsavedEdits(true);
  }, [axes]);


  useEffect(() => {
    // A restored autosave replaces the loaded annotation state entirely.
    setTranscriptConversionNotice(null);
    if (restoredAxes) {
      isLoadingData.current = true;
      globalAxisId = highestAxisId(restoredAxes) + 1;
      setAxes(clampAxesToDuration(restoredAxes, duration));
      return;
    }

    // Edits carried from the last time this chunk was open in this session.
    // Session state rather than recovery, so it applies silently: as far as the
    // user is concerned they never left.
    if (carriedAxes) {
      isLoadingData.current = true;
      globalAxisId = highestAxisId(carriedAxes) + 1;
      setAxes(clampAxesToDuration(carriedAxes, duration));
      return;
    }

    isLoadingData.current = true;
    const newAxes: AxisData[] = (Array.isArray(annotationData) ? annotationData : []).map((axisData) => ({
      id: globalAxisId++,
      type: axisData.axisType,
      axisName: axisData.axisName,
      typeName: axisData.axisBooklistName,
      blocks: axisData.annotationBlocks.map((block) =>
        clampBlockToDuration(block, duration)
      ),
    }));
    setAxes(newAxes);
  }, [restoredAxes, carriedAxes, annotationData, setAxes, duration]);

  const handleConvertTranscript = () => {
    if (!speakerData?.length || switchingChunk) return;
    const result = convertTranscriptToAnnotations(axes, speakerData, duration, globalAxisId);
    globalAxisId = result.nextAxisId;
    if (result.addedBlocks) setAxes(result.axes);
    const axisCount = result.addedAxes + result.reusedAxes;
    const messages = [result.addedBlocks
      ? `Added ${result.addedBlocks} annotation ${result.addedBlocks === 1 ? "block" : "blocks"} on ${axisCount} speaker ${axisCount === 1 ? "axis" : "axes"}.`
      : "No annotations were added."];
    if (result.skippedSpeakers) {
      messages.push(`Skipped ${result.skippedSpeakers} ${result.skippedSpeakers === 1 ? "speaker" : "speakers"} because matching axes contain annotations, use a different type, or have duplicate names.`);
    }
    if (result.skippedSegments) {
      messages.push(`Skipped ${result.skippedSegments} transcript ${result.skippedSegments === 1 ? "segment" : "segments"} with invalid timestamps or times outside the current timeline.`);
    }
    setTranscriptConversionNotice(messages.join(" "));
  };

  const handleCreateBlock = useCallback((axisId: number) => {
    const newBlock = clampBlockToDuration({
      start: selectedRange[0],
      end: selectedRange[1],
      text: "",
    }, duration);

    const axis = axes.find((candidateAxis) => candidateAxis.id === axisId);
    if (axis) {
      const hasOverlap = axis.blocks.some(
        (block) => newBlock.start <= block.end && newBlock.end >= block.start
      );

      if (hasOverlap) {
        setError(
          "Error: Block overlaps with an existing block. Create a new axis or adjust the range."
        );
        setIsErrorDialogOpen(true);
        return;
      }
    }

    setError("");
    setIsErrorDialogOpen(false);
    setAxes((currentAxes) =>
      currentAxes.map((currentAxis) =>
        currentAxis.id === axisId
          ? { ...currentAxis, blocks: [...currentAxis.blocks, newBlock] }
          : currentAxis
      )
    );
  }, [axes, selectedRange, setAxes, duration]);

  useEffect(() => {
    const handleKeyPress = (event: KeyboardEvent) => {
      if (switchingChunk) return;
      if (
        event.target instanceof HTMLElement &&
        event.target.tagName === "INPUT"
      ) {
        return;
      }

      const pressedKey = event.key;
      const targetedAxes = axes.filter(
        (axis) => axis.shortcutKey === pressedKey
      );
      targetedAxes.forEach((axis) => {
        handleCreateBlock(axis.id);
      });
    };

    window.addEventListener("keydown", handleKeyPress);
    return () => {
      window.removeEventListener("keydown", handleKeyPress);
    };
  }, [axes, handleCreateBlock, switchingChunk]);

  const handleOpenSaveDialog = useCallback(() => {
    // Prefer the file this session is working in, so a save goes back to the
    // file it came from. The merge in a chunk save depends on this: a
    // different name merges into a file that does not exist.
    const defaultName =
      savedAnnotationName ||
      buildDefaultAnnotationName(rosBagFileName, bookListFileName);
    setAnnotationName(defaultName);
    setIsSaveDialogOpen(true);
  }, [savedAnnotationName, rosBagFileName, bookListFileName]);

  useEffect(() => {
    onSaveReady?.(handleOpenSaveDialog);
    return () => onSaveReady?.(null);
  }, [onSaveReady, handleOpenSaveDialog]);


  const finishSave = (name: string) => {
    alert("Data saved successfully.");
    setHasUnsavedEdits(false);
    autosave.markSynced(axes);
    // Later saves in this session default to the file just written, including
    // after a chunk switch.
    onAnnotationSaved?.(name);
    if (autosaveEnabled) {
      deleteAutosave(rosBagFileName, autosaveScope).catch((err) =>
        console.warn(" [autosave] Could not clear autosave after save.", err)
      );
    }
  };

  const attemptSave = async (
    name: string,
    data: AnnotationAxisPayload[],
    confirmOverwrite: boolean,
  ) => {
    try {
      const result = await postAnnotation(name, data, {
        confirmOverwrite,
        scope: autosaveScope,
        source: {
          bag_filename: rosBagFileName,
          source_duration: sourceDuration,
        },
      });
      if (result.status === "conflict") {
        setPendingOverwrite({ name, data, conflict: result.conflict });
        return;
      }
      finishSave(name);
    } catch (error) {
      setError("Failed to save data. Please try again.\n" + error);
      setIsErrorDialogOpen(true);
    }
  };

  const handleConfirmSave = async () => {
    const validation = isValidAnnotationName(annotationName);
    if (!validation.valid) {
      setError(validation.reason || "Invalid name.");
      setIsErrorDialogOpen(true);
      return;
    }

    setIsSaveDialogOpen(false);
    await attemptSave(annotationName, collectAnnotationData(axes), false);
  };

  const handleConfirmOverwrite = async () => {
    if (!pendingOverwrite) return;
    const { name } = pendingOverwrite;
    setPendingOverwrite(null);
    // Re-collect rather than reusing the snapshot from the first attempt, so
    // anything created while the prompt was open is included.
    await attemptSave(name, collectAnnotationData(axes), true);
  };

  // Cancelling returns to the name dialog: the usual next step is choosing a
  // different name rather than abandoning the save.
  const handleCancelOverwrite = () => {
    setPendingOverwrite(null);
    setIsSaveDialogOpen(true);
  };



  const handleDragEnd = (result: DropResult) => {
    const { source, destination } = result;


    if (!destination) return;


    const sourceAxis = axes.find((axis) => String(axis.id) === source.droppableId);
    const destinationAxis = axes.find((axis) => String(axis.id) === destination.droppableId);


    if (sourceAxis && destinationAxis) {
      if (sourceAxis == destinationAxis) return;
      const sourceBlocks = [...sourceAxis.blocks];
      const destinationBlocks = [...destinationAxis.blocks];


      const [movedBlock] = sourceBlocks.splice(source.index, 1);


      destinationBlocks.splice(destination.index, 0, movedBlock);


      setAxes((prevAxes) =>
        prevAxes.map((axis) => {
          if (axis.id === sourceAxis.id) {
            return { ...axis, blocks: sourceBlocks };
          } else if (axis.id === destinationAxis.id) {
            return { ...axis, blocks: destinationBlocks };
          } else {
            return axis;
          }
        })
      );
    }
  };
  const handleRangeChange = (_event: Event, newValue: number | number[]) => {
    setSelectedRange(newValue as number[]);
  };

  const handleAddAxis = () => {
    setAxes((prev) => [
      ...prev,
      { id: globalAxisId++, type: "type-in", axisName:String(globalAxisId-1) ,blocks: [] },
    ]);
  };
  const handleDeleteBlock = (axisId: number, blockIndex: number) => {
    setPendingDeletion({ kind: "block", axisId, blockIndex });
  };

  const handleDeleteAxis = (axisId: number) => {
    setPendingDeletion({ kind: "axis", axisId });
  };

  const confirmDeletion = () => {
    if (!pendingDeletion) return;

    if (pendingDeletion.kind === "axis") {
      setAxes((currentAxes) =>
        currentAxes.filter((axis) => axis.id !== pendingDeletion.axisId)
      );
    } else {
      setAxes((currentAxes) =>
        currentAxes.map((axis) =>
          axis.id === pendingDeletion.axisId
            ? {
                ...axis,
                blocks: axis.blocks.filter(
                  (_, index) => index !== pendingDeletion.blockIndex
                ),
              }
            : axis
        )
      );
    }

    setPendingDeletion(null);
  };

  const handleTypeChange = (
    axisId: number,
    type: string,
    typeName?: string
  ) => {
    setAxes((axes) =>
      axes.map((axis) => {
        if (axis.id === axisId) {
          return { ...axis, type, typeName };
        }
        return axis;
      })
    );
  };

  const handleNameChange = (axisId: number, axisName: string) => {
    if (isDuplicateAxisName(axes, axisId, axisName)) {
      setError(`An axis named "${axisName.trim()}" already exists. Use a unique name.`);
      setIsErrorDialogOpen(true);
      return;
    }
    setError("");
    setAxes((axes) =>
      axes.map((axis) => {
        if (axis.id === axisId) {
          return { ...axis, axisName: axisName };
        }
        return axis;
      })
    );
  };

  const handleSave = (axisId: number, blockIndex: number, newText: string, newstart:number, newend:number) => {
    setAxes(
      axes.map((axis) => {
        if (axis.id === axisId) {
          const newBlocks = axis.blocks.map((block, index) => {
            if (index === blockIndex) {
              return clampBlockToDuration(
                { ...block, text: newText, start: newstart, end: newend },
                duration,
              );
            }
            return block;
          });
          return { ...axis, blocks: newBlocks };
        }
        return axis;
      })
    );
  };

  const marks = Array.from(
    { length: Math.ceil(duration / markInterval) },
    (_, index) => {
      const value = Math.round(markInterval * index);
      return {
        value: value,
        label: `${value}s`,
      };
    }
  );

  const handleShortcutChange = (axisId: number, shortcutKey: string) => {
    setAxes((axes) =>
      axes.map((axis) => {
        if (axis.id === axisId) {
          return { ...axis, shortcutKey };
        }
        return axis;
      })
    );
  };
  const handleDoubleClickCreateBlock = (axisId: number, startTime: number) => {
    const newBlock = clampBlockToDuration({
      start: startTime,
      end: startTime + 5,
      text: "New Block",
    }, duration);

    const axis = axes.find((axis) => axis.id === axisId);
    if (axis) {
      const overlap = axis.blocks.some(
        (block) => newBlock.start <= block.end && newBlock.end >= block.start
      );

      if (overlap) {
        setError(
          "Error: Block overlaps with an existing block. Create a new axis or adjust the range."
        );
        setIsErrorDialogOpen(true);
        return;
      }
    }

    setError("");
    setIsErrorDialogOpen(false);
    setAxes((prevAxes) =>
      prevAxes.map((axis) => {
        if (axis.id === axisId) {
          const updatedBlocks = [...axis.blocks, newBlock];
          return { ...axis, blocks: updatedBlocks };
        }
        return axis;
      })
    );
  };
  const totalWidth = (duration / markInterval) * 50;

  const conflict = pendingOverwrite?.conflict;
  const chunkRange = conflict
    ? `${formatSeconds(conflict.chunk_start_seconds)} to ${formatSeconds(conflict.chunk_end_seconds)}`
    : "";
  const chunkLabel = conflict?.chunk_index !== undefined
    ? `chunk ${conflict.chunk_index + 1}`
    : "this chunk";

  const overwritePrompt = (() => {
    if (!conflict) return null;
    const file = `"${conflict.annotation_name}.csv"`;

    if (conflict.reason === "file_unreadable") {
      return {
        title: "That file could not be read",
        body: `${file} already exists but could not be read as an annotation file. Saving replaces it completely, and whatever it currently holds will be lost.`,
        cancel: "Choose another name",
        confirm: "Replace file",
        destructive: true,
      };
    }

    if (conflict.reason === "chunk_is_empty") {
      return {
        title: "Add to the existing file?",
        body: `${file} already holds ${conflict.block_count ?? 0} annotations from other parts of the recording, but none in ${chunkLabel} (${chunkRange}). Your work for this chunk will be added to it.`,
        cancel: "Choose another name",
        confirm: "Add to file",
        destructive: false,
      };
    }

    if (conflict.reason === "chunk_has_annotations") {
      return {
        title: "Replace this chunk's annotations?",
        body: `${file} already holds ${conflict.chunk_block_count ?? 0} annotations in ${chunkLabel} (${chunkRange}). Saving replaces them with your current work. Annotations elsewhere in the recording are kept.`,
        cancel: "Choose another name",
        confirm: "Replace this chunk",
        destructive: true,
      };
    }

    return {
      title: "Replace the existing annotation file?",
      body: `${file} was last saved at ${formatAutosaveTimestamp(conflict.modified_at)} and holds ${conflict.axis_count ?? 0} time ${conflict.axis_count === 1 ? "axis" : "axes"} and ${conflict.block_count ?? 0} annotations. Saving replaces all of it with your current work.`,
      cancel: "Choose another name",
      confirm: "Replace file",
      destructive: true,
    };
  })();

  const pendingBlock = pendingDeletion?.kind === "block"
    ? axes
        .find((axis) => axis.id === pendingDeletion.axisId)
        ?.blocks[pendingDeletion.blockIndex]
    : undefined;
  const boundaryToleranceSeconds = 0.001;
  const touchesPreviousChunk = Boolean(
    pendingBlock &&
    autosaveScope &&
    autosaveScope.chunk_index > 0 &&
    Math.abs(pendingBlock.start) <= boundaryToleranceSeconds
  );
  const touchesNextChunk = Boolean(
    pendingBlock &&
    autosaveScope &&
    autosaveScope.chunk_index < chunkCount - 1 &&
    Math.abs(pendingBlock.end - duration) <= boundaryToleranceSeconds
  );
  const isBoundaryBlockDeletion = touchesPreviousChunk || touchesNextChunk;

  return (
    <DragDropContext onDragEnd={handleDragEnd}>
    <MainContainer>
      <Dialog
        open={isErrorDialogOpen}
        onClose={() => setIsErrorDialogOpen(false)}
      >
        <DialogTitle>Error</DialogTitle>
        <DialogContent>
          <DialogContentText>{error}</DialogContentText>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setIsErrorDialogOpen(false)}>Close</Button>
        </DialogActions>
      </Dialog>
<Dialog
  open={isSaveDialogOpen}
  onClose={() => setIsSaveDialogOpen(false)}
>
  <DialogTitle>Name Your Annotation</DialogTitle>
  <DialogContent>
    <DialogContentText>
      Enter a name to save this annotation under. Reusing an existing name replaces
      that file, and you will be asked to confirm first.
    </DialogContentText>
    <TextField
      autoFocus
      margin="dense"
      label="Annotation Name"
      fullWidth
      variant="outlined"
      value={annotationName}
      onChange={(event) => setAnnotationName(event.target.value)}
    />
  </DialogContent>
  <DialogActions>
    <Button onClick={() => setIsSaveDialogOpen(false)}>Cancel</Button>
    <Button onClick={handleConfirmSave} variant="contained">
      Save
    </Button>
  </DialogActions>
</Dialog>
<Dialog open={pendingOverwrite !== null} disableEscapeKeyDown>
  <DialogTitle>{overwritePrompt?.title}</DialogTitle>
  <DialogContent>
    <DialogContentText>{overwritePrompt?.body}</DialogContentText>
  </DialogContent>
  <DialogActions>
    <Button onClick={handleCancelOverwrite}>{overwritePrompt?.cancel}</Button>
    <Button
      onClick={handleConfirmOverwrite}
      color={overwritePrompt?.destructive ? "error" : "primary"}
      variant="contained"
    >
      {overwritePrompt?.confirm}
    </Button>
  </DialogActions>
</Dialog>
<Dialog
  open={pendingDeletion !== null}
  onClose={() => setPendingDeletion(null)}
>
  <DialogTitle sx={{ color: isBoundaryBlockDeletion ? "error.main" : undefined }}>
    {pendingDeletion?.kind === "axis"
      ? "Delete annotation timeline?"
      : isBoundaryBlockDeletion
      ? "Delete annotation block at chunk boundary?"
      : "Delete annotation block?"}
  </DialogTitle>
  <DialogContent>
    <DialogContentText>
      {isBoundaryBlockDeletion
        ? "This annotation touches a chunk boundary. Deleting this part only removes it from the current chunk; the corresponding part in the adjacent chunk will not be deleted. This action cannot be undone."
        : "This action cannot be undone. Are you sure you want to continue?"}
    </DialogContentText>
  </DialogContent>
  <DialogActions>
    <Button onClick={() => setPendingDeletion(null)}>Cancel</Button>
    <Button onClick={confirmDeletion} color="error" variant="contained">
      Delete
    </Button>
  </DialogActions>
</Dialog>
      <ControlsContainer>
        <Button onClick={handleOpenSaveDialog} variant="contained">
          Save and Send Data
        </Button>
        <Button onClick={handleAddAxis} variant="contained">
          Add New Axis
        </Button>
        <Tooltip title={speakerData?.length
          ? "Convert the current transcript by speaker. Empty type-in axes can be reused; populated axes are preserved."
          : "A transcript with speaker segments is required."}>
          <span>
            <Button onClick={handleConvertTranscript} variant="contained" disabled={!speakerData?.length || switchingChunk}>
              Convert Transcript to Annotations
            </Button>
          </span>
        </Tooltip>
        <Button onClick={() => setIsDialogOpen(true)} variant="contained">
          Manage Axes
        </Button>
      </ControlsContainer>
      {transcriptConversionNotice && (
        <Alert severity="info" onClose={() => setTranscriptConversionNotice(null)} sx={{ mb: 2 }}>
          {transcriptConversionNotice}
        </Alert>
      )}
      <ScrollableTimelineContainer>
        <TimelineGrid style={{ width: `${totalWidth + 170}px` }}>
          <DurationLabel>Annotation Duration</DurationLabel>
          <DurationTimelineCell>
            <AxisManager
              open={isDialogOpen}
              onClose={() => setIsDialogOpen(false)}
              axes={axes}
              booklist={booklist}
              onDeleteAxis={handleDeleteAxis}
              onTypeChange={handleTypeChange}
              onShortcutChange={handleShortcutChange}
              onNameChange={handleNameChange}
            />
            <Slider
              value={selectedRange}
              min={0}
              max={duration}
              step={markInterval} // Ensure the step is the same as markInterval
              onChange={handleRangeChange}
              valueLabelDisplay="auto"
              sx={{ margin: 0 }}
              marks={marks.map((mark) => ({ value: mark.value, label: "" }))}
            />
          </DurationTimelineCell>
          <TimelineControlCell aria-hidden="true" />
          <TimelineMarksCell>
            <TimelineMarks>
              {marks.map((mark, index) => (
                <TimelineMarkLabel
                  key={index}
                  style={{ left: `${(mark.value / duration) * 100}%` }}
                >
                  {mark.label}
                </TimelineMarkLabel>
              ))}
            </TimelineMarks>
          </TimelineMarksCell>
          {axes.map((axis) => (
            <React.Fragment key={axis.id}>
              <AxisControlCell>
                <Button
                  onClick={() => handleCreateBlock(axis.id)}
                  variant="contained"
                  sx={{ width: "150px", height: "42px" }}
                >
                  Create
                </Button>
              </AxisControlCell>
              <Axis
                id={axis.id}
                duration={duration}
                selectedRange={selectedRange}
                blocks={axis.blocks}
                axisType={axis.type}
                axisName={axis.axisName || "No Axis Name"}
                booklist={axis.typeName ? booklist[axis.typeName] || [] : []}
                onSave={(blockIndex, text, start, end) =>
                  handleSave(axis.id, blockIndex, text, start, end)
                }
                onDeleteBlock={(blockIndex) =>
                  handleDeleteBlock(axis.id, blockIndex)
                }
                onDoubleClickCreateBlock={handleDoubleClickCreateBlock}
              />
            </React.Fragment>
          ))}
        </TimelineGrid>
      </ScrollableTimelineContainer>
    </MainContainer>
    </DragDropContext>
  );
};

export default Timeline;
