import React, { useState, useEffect, useContext, useRef } from "react";
import { DragDropContext, DropResult } from 'react-beautiful-dnd';
import {
  Button,
  Slider,
  Paper,
  Dialog,
  DialogTitle,
  DialogActions,
  DialogContent,
  DialogContentText,
  TextField,
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
import { applyAIInstruction } from "./aiInstruction";

let globalAxisId = 1;

interface TimelineProps {
  duration: number;
  played: number;
  onSeek: (time: number) => void;
  rosBagFileName: string;
  bookListFileName: string;
  booklist: any;
  annotationData: any;
  speakerData?: Array<any>;
  restoredAxes?: any[] | null;
  autosaveEnabled?: boolean;
  autosaveScope?: AutosaveScope;
  onAutosaveReady?: (flush: (() => Promise<void>) | null) => void;
  switchingChunk?: boolean;
  onAxesUpdate: (axes: any) => void;
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
  justifyContent: "space-between",
  alignItems: "center",
  marginBottom: "20px",
  width: "100%",
});

const ScrollableTimelineContainer = styled("div")({
  overflowX: "scroll",
  overflowY: "hidden",
  width: "100%",
  padding: "10px 0",
  position: "relative",
});

const ButtonsContainer = styled("div")({
  display: "flex",
  flexDirection: "column",
  padding: "10px",
  alignItems: "flex-start",
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
  played,
  onSeek,
  rosBagFileName,
  bookListFileName,
  booklist,
  annotationData,
  speakerData,
  onAxesUpdate,
  instruction,
  restoredAxes,
  autosaveEnabled = true,
  autosaveScope,
  onAutosaveReady,
  onSaveReady,
  switchingChunk = false,
  savedAnnotationName,
  onAnnotationSaved
}) => {
  const [seekTime, setSeekTime] = useState(played);
  const [markInterval] = useState(1);
  const [selectedRange, setSelectedRange] = useState<number[]>([
    0,
    0.1 * duration,
  ]);
  const [isDialogOpen, setIsDialogOpen] = useState(false);
  const [error, setError] = useState("");
  const [isErrorDialogOpen, setIsErrorDialogOpen] = useState(false);
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
    data: any;
    conflict: AnnotationSaveConflict;
  } | null>(null);
  const [hasUnsavedEdits, setHasUnsavedEdits] = useState(false);
  

  const autosave = useAutosave({
    enabled: autosaveEnabled && Boolean(rosBagFileName),
    bagFileName: rosBagFileName,
    scope: autosaveScope,
    axes,
    hasUnsavedEdits: hasUnsavedEdits || Boolean(autosaveScope),
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
    }
  }, [restoredAxes, markSynced]);

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
    // A restored autosave replaces the loaded state entirely. It already
    // contains the speaker tiers from the session it was saved in, so the
    // branches below must not run as well.
    if (restoredAxes) {
      isLoadingData.current = true;
      globalAxisId = highestAxisId(restoredAxes) + 1;
      setAxes(restoredAxes);
      return;
    }

    isLoadingData.current = true;
    const newAxes = (Array.isArray(annotationData) ? annotationData : []).map((axisData: any) => ({
      id: globalAxisId++,
      type: axisData.axisType,
      axisName: axisData.axisName,
      typeName: axisData.axisBooklistName,
      blocks: axisData.annotationBlocks,
    }));
    if (speakerData) {
      const speakerAxesMap = new Map<string, any>();
      speakerData.forEach((segment) => {
        const speakerLabel = segment.speaker_label;

        if (speakerAxesMap.has(speakerLabel)) {
          const existingAxis = speakerAxesMap.get(speakerLabel);
          existingAxis.blocks.push({
            start: segment.start_time,
            end: segment.end_time,
            text: segment.text,
          });
        } else {
          speakerAxesMap.set(speakerLabel, {
            id: globalAxisId++,
            type: "Type-in",
            axisName: speakerLabel,
            blocks: [
              {
                start: segment.start_time,
                end: segment.end_time,
                text: segment.text,
              },
            ],
            shortcutKey: speakerLabel.charAt(0).toUpperCase(),
          });
        }
      });

      const speakerAxes = Array.from(speakerAxesMap.values());
      newAxes.push(...speakerAxes);
    }
    setAxes(newAxes);
  }, [restoredAxes, annotationData, speakerData]);

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
  }, [axes, selectedRange, switchingChunk]);

  useEffect(() => {
    setSeekTime(played);
  }, [played]);

  const handleOpenSaveDialog = () => {
    // Prefer the file this session is working in, so a save goes back to the
    // file it came from. The merge in a chunk save depends on this: a
    // different name merges into a file that does not exist.
    const defaultName =
      savedAnnotationName ||
      buildDefaultAnnotationName(rosBagFileName, bookListFileName);
    setAnnotationName(defaultName);
    setIsSaveDialogOpen(true);
  };

  useEffect(() => {
    onSaveReady?.(handleOpenSaveDialog);
    return () => onSaveReady?.(null);
  });


  const finishSave = (name: string) => {
    alert("Data saved successfully.");
    setHasUnsavedEdits(false);
    autosave.markSynced(axes);
    // Later saves in this session default to the file just written, including
    // after a chunk switch.
    onAnnotationSaved?.(name);
    if (autosaveEnabled && !autosaveScope) {
      deleteAutosave(rosBagFileName).catch((err) =>
        console.warn(" [autosave] Could not clear autosave after save.", err)
      );
    }
  };

  const attemptSave = async (
    name: string,
    data: any,
    confirmOverwrite: boolean,
  ) => {
    try {
      const result = await postAnnotation(name, data, {
        confirmOverwrite,
        scope: autosaveScope,
      });
      if (result.status === "conflict") {
        setPendingOverwrite({ name, data, conflict: result.conflict });
        return;
      }
      if (autosaveScope) await autosave.flush();
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



  const handleSliderChange = (_event: Event, newValue: number | number[]) => {
    setSeekTime(newValue as number);
    onSeek(newValue as number);
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
  const handleCreateBlock = (axisId: number) => {
    const newBlock = {
      start: selectedRange[0],
      end: selectedRange[1],
      text: "",
    };

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
              return { ...block, text: newText, start:newstart, end:newend };
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
    const newBlock = {
      start: startTime,
      end: startTime + 5,
      text: "New Block",
    };

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
  <DialogTitle>
    {pendingDeletion?.kind === "axis"
      ? "Delete annotation timeline?"
      : "Delete annotation block?"}
  </DialogTitle>
  <DialogContent>
    <DialogContentText>
      This action cannot be undone. Are you sure you want to continue?
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
        <Button onClick={() => setIsDialogOpen(true)} variant="contained">
          Manage Axes
        </Button>
      </ControlsContainer>
      <div style={{ display: "flex", width: "100%" }}>
        <ButtonsContainer>
          {axes.map((axis, index) => (
            <Button
              key={index}
              onClick={() => handleCreateBlock(axis.id)}
              variant="contained"
              sx={{
                mb: 2.25,
                top: "145px",
                width: "150px",
                height: "42px",
              }}
            >
              Create
            </Button>
          ))}
        </ButtonsContainer>
        <ScrollableTimelineContainer>
          <div style={{ width: `${totalWidth}px`, padding: "10px" }}>
            <Slider
              value={seekTime}
              min={0}
              max={duration}
              step={markInterval}
              onChange={handleSliderChange}
              valueLabelDisplay="off"
              marks={marks.map((mark) => ({ value: mark.value, label: "" }))}
              sx={{
                "& .MuiSlider-track": { backgroundColor: "transparent" },
                "& .MuiSlider-thumb": {
                  width: "20px",
                  height: "20px",
                  "&:before": { boxShadow: "0 4px 8px rgba(0,0,0,0.4)" },
                },
                "& .MuiSlider-rail": { height: "8px", opacity: 0.5 },
              }}
            />
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
              sx={{ marginTop: "20px", marginBottom: "20px" }}
              marks={marks.map((mark) => ({ value: mark.value, label: "" }))}
            />
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
            {axes.map((axis) => (
              <Axis
                key={axis.id}
                id = {axis.id}
                duration={duration}
                selectedRange={selectedRange}
                blocks={axis.blocks}
                axisType={axis.type}
                axisName={axis.axisName || "No Axis Name"}
                booklist={axis.typeName ? booklist[axis.typeName] || [] : []}
                onSave={(blockIndex, text,start,end) =>
                  handleSave(axis.id, blockIndex, text,start,end)
                }
                onDeleteBlock={(blockIndex) =>
                  handleDeleteBlock(axis.id, blockIndex)
                }
                onDoubleClickCreateBlock={handleDoubleClickCreateBlock}
              />
            ))}
          </div>
        </ScrollableTimelineContainer>
      </div>
    </MainContainer>
    </DragDropContext>
  );
};

export default Timeline;
