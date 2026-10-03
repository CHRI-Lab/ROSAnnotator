import { useCallback, useEffect, useRef, useState } from "react";
import ReactPlayer from "react-player";
import {
  Box,
  Button,
  CircularProgress,
  Dialog,
  DialogActions,
  DialogContent,
  DialogContentText,
  DialogTitle,
  FormControl,
  MenuItem,
  Paper,
  Select,
  Slider,
  Typography,
} from "@mui/material";

import type { ChunkManifest } from "../../api/chunks";
import AppHeader from "../../components/AppHeader";
import {
  AxesProvider,
  type AxisData,
} from "../../components/AxesProvider/AxesContext";
import Booklist from "../../components/Booklist/Booklist";
import Chatbox from "../../components/Chatbox";
import EditBooklistForm from "../../components/EditBooklistForm/EditBooklistForm";
import FrontEndWorkspace from "../../components/FrontEndWorkspace";
import RightAssistantPanel from "../../components/RightAssistantPanel";
import Timeline from "../../components/Timeline";
import {
  applyAIInstruction,
  requiresAIChangeConfirmation,
} from "../../components/Timeline/aiInstruction";
import {
  AssistantMode,
  AssistantReply,
  AssistantRouting,
} from "../../types/assistantRouting";
import {
  AIInstruction,
  AIRecord,
  AssistantRequestOptions,
  buildAIRecordAnnotationName,
} from "../../types/aiRecords";

import type { BackendDataView } from "../../components/FrontEndWorkspace/viewTypes";

interface AnnotatorProps {
  rosBagFileName?: string;
  bookListFileName?: string;
  data: any;
  bookListData: any;
  chunkManifest?: ChunkManifest | null;
  currentChunkIndex?: number;
  switchingChunk?: boolean;
  onChunkChange?: (index: number) => void | Promise<void>;
  restoredAxes?: any[] | null;
  autosaveEnabled?: boolean;
  onAutosaveReady?: (flush: (() => Promise<void>) | null) => void;
  savedAnnotationName?: string;
  onAnnotationSaved?: (name: string) => void;
}

const Annotator = ({
  rosBagFileName = "",
  bookListFileName = "",
  data,
  bookListData,
  chunkManifest = null,
  currentChunkIndex = 0,
  switchingChunk = false,
  onChunkChange = () => {},
  restoredAxes = null,
  autosaveEnabled = true,
  onAutosaveReady,
  savedAnnotationName = "",
  onAnnotationSaved,
}: AnnotatorProps) => {
  const [player, setPlayer] = useState<ReactPlayer | null>(null);
  const [duration, setDuration] = useState(data.duration_seconds || 0);
  const [played, setPlayed] = useState(0);
  const [isPlaying, setIsPlaying] = useState(false);
  const [editMode, setEditMode] = useState(false);
  const [bookList, setBookList] = useState(bookListData);
  const [axesData, setAxesData] = useState<AxisData[]>([]);
  const [instruction, setInstruction] = useState<AIInstruction | null>(null);
  const [pendingAIChange, setPendingAIChange] = useState<{
    instruction: AIInstruction;
    resolve: (accepted: boolean) => void;
  } | null>(null);
  const [aiRecords, setAIRecords] = useState<AIRecord[]>(data.ai_records ?? []);
  const [conversationKey, setConversationKey] = useState(0);
  const [pendingChunkIndex, setPendingChunkIndex] = useState<number | null>(null);
  const [confirmingChunkSwitch, setConfirmingChunkSwitch] = useState(false);
  const [chunkSwitchError, setChunkSwitchError] = useState("");

  // Timeline owns the save dialog; the header button opens it.
  const openSaveDialog = useRef<(() => void) | null>(null);
  const registerSaveDialog = useCallback(
    (open: (() => void) | null) => {
      openSaveDialog.current = open;
    },
    [],
  );

  // Timeline's duration is chunk-local in a chunked session. The source length
  // must always describe the whole recording, so take it from the manifest
  // whenever there is one.
  const sourceDuration = chunkManifest
    ? chunkManifest.duration_seconds
    : data.duration_seconds || duration;

  const handleClearConversation = async () => {
    const response = await fetch("http://localhost:8000/api/gpt_chat/clear/", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ chat_context_id: data.chat_context_id }),
    });
    if (!response.ok) {
      throw new Error("Could not clear backend conversation history");
    }
    setConversationKey((key) => key + 1);
  };
  useEffect(() => {
    if (bookListData) {
      setBookList(bookListData);
    } else {
      setBookList([]);
    }
    setAIRecords(data.ai_records ?? []);
  }, [data, bookListData]);

  const upsertAIRecord = (record: AIRecord) => {
    setAIRecords((currentRecords) => {
      const existingIndex = currentRecords.findIndex(
        (currentRecord) => currentRecord.run_id === record.run_id,
      );
      if (existingIndex === -1) {
        return [...currentRecords, record];
      }

      return currentRecords.map((currentRecord, index) =>
        index === existingIndex ? record : currentRecord,
      );
    });
  };

  const processingPending = Object.values((data.views || {}) as Record<string, BackendDataView>).some(view => view.status === 'loading');
  useEffect(() => { setDuration(data.duration_seconds || 0); }, [data.duration_seconds]);

  const persistCompletedAIRecord = async (
    record: AIRecord | undefined,
    outcome: "replied" | "applied" | "rejected" | "not_applied",
  ) => {
    if (!record) throw new Error("AI response did not include a record to save.");
    const annotationName = buildAIRecordAnnotationName(
      rosBagFileName,
      bookListFileName,
    );
    const response = await fetch("http://localhost:8000/api/ai_records/complete/", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        annotation_name: annotationName,
        ...(chunkManifest ? {
          manifest_id: chunkManifest.id,
          chunk_index: currentChunkIndex,
        } : {}),
        ai_record: record,
        outcome,
      }),
    });
    if (!response.ok) {
      throw new Error("The AI reply completed, but its record could not be saved. Please retry.");
    }
    upsertAIRecord({ ...record, action_outcome: outcome });
  };

  const handleAxesUpdate = useCallback((updatedAxes) => {
    setAxesData(updatedAxes);
    return updatedAxes;
  }, []);

  const requestAIChangeConfirmation = (pendingInstruction: AIInstruction) =>
    new Promise<boolean>((resolve) => {
      setPendingAIChange({ instruction: pendingInstruction, resolve });
    });

  const resolveAIChangeConfirmation = (accepted: boolean) => {
    pendingAIChange?.resolve(accepted);
    setPendingAIChange(null);
  };

  const handleSendMessageToGPT = (
    message: string,
    assistantRouting: AssistantRouting,
    options?: AssistantRequestOptions,
  ) => {
    if (processingPending) return Promise.resolve({ text: "Please wait for annotation data to finish loading.", isError: true } as AssistantReply);
    return fetch("http://localhost:8000/api/gpt_chat/", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        message: message, 
        audio_transcript: data.audio_transcript, 
        video_path: data.video_path,
        Axeinfo: axesData,
        Codebook: bookList,
        chat_context_id: data.chat_context_id,
        assistant_mode: assistantRouting.mode,
        context_routes: assistantRouting.contextRoutes,
        fallback_consent: options?.fallbackConsent
          ? {
              from: options.fallbackConsent.from,
              to: options.fallbackConsent.to,
              user_consented: options.fallbackConsent.userConsented,
            }
          : undefined,
      }),
    })
      .then(async (response) => {
        const responseData = await response.json().catch(() => ({}));
        if (!response.ok) {
          const error = new Error(
            responseData.error || "The AI assistant could not complete the request.",
          ) as Error & {
            assistantMode?: AssistantMode;
            canFallbackToRemote?: boolean;
            canFallbackToLocal?: boolean;
          };
          error.assistantMode =
            responseData.assistant_mode ?? assistantRouting.mode;
          error.canFallbackToRemote = responseData.can_fallback_to_remote;
          error.canFallbackToLocal = responseData.can_fallback_to_local;
          throw error;
        }
        return responseData;
      })
      .then(async (data) => {
        const responseString = data.response;
        const assistantMode =
          (data.assistant_mode as AssistantMode) ?? assistantRouting.mode;
        const aiRecord = data.ai_record as AIRecord | undefined;

        const jsonStartIndex = responseString.indexOf("{");
        const jsonEndIndex = responseString.lastIndexOf("}");
  
        if (jsonStartIndex !== -1 && jsonEndIndex !== -1 && jsonEndIndex > jsonStartIndex) {

          const normalMessage = responseString.substring(0, jsonStartIndex).trim();
          const jsonString = responseString.substring(jsonStartIndex, jsonEndIndex + 1).trim();
  
          let parsedObject: unknown;
          try {
            parsedObject = JSON.parse(jsonString);
          } catch (error) {
            console.error("Failed to parse JSON:", error);
          }

          if (
            parsedObject && typeof parsedObject === "object" &&
            "type" in parsedObject && parsedObject.type === "instruction" &&
            "steps" in parsedObject && Array.isArray(parsedObject.steps)
          ) {
              console.log("This is an instruction:", parsedObject);
              const parsedInstruction = parsedObject as AIInstruction;
              if (
                requiresAIChangeConfirmation(parsedInstruction, axesData) &&
                !(await requestAIChangeConfirmation(parsedInstruction))
              ) {
                await persistCompletedAIRecord(aiRecord, "rejected");
                return {
                  text: "AI timeline changes were cancelled. No annotation changes were applied.",
                  assistantMode,
                  aiRecord,
                  isError: true,
                };
              }
              const updatedAxes = applyAIInstruction(axesData, parsedInstruction, duration);
              const requestedAnnotation = /\bannotat(?:e|ion|ions|ing)\b/i.test(message);
              const addedBlockApplied = parsedInstruction.steps.some((step) => {
                if (step.action !== "addBlock") return false;
                const axisId = Number(step.parameters?.axisId);
                const start = Number(step.parameters?.start);
                const end = Number(step.parameters?.end);
                const text = String(step.parameters?.text ?? "");
                const wasPresent = axesData.find((axis) => axis.id === axisId)?.blocks.some(
                  (block) => block.start === start && block.end === end && block.text === text,
                );
                const isPresent = updatedAxes.find((axis) => axis.id === axisId)?.blocks.some(
                  (block) => block.start === start && block.end === end && block.text === text,
                );
                return Boolean(isPresent && !wasPresent);
              });
              if (requestedAnnotation && !addedBlockApplied) {
                await persistCompletedAIRecord(aiRecord, "not_applied");
                return {
                  text: "The model did not provide any usable annotation blocks. No empty axis was created. Please try again with a specific time range or annotation target.",
                  assistantMode,
                  aiRecord,
                  isError: true,
                };
              }
              if (JSON.stringify(updatedAxes) === JSON.stringify(axesData)) {
                await persistCompletedAIRecord(aiRecord, "not_applied");
                return {
                  text: "The model returned a timeline instruction, but none of its steps could be applied.",
                  assistantMode,
                  aiRecord,
                  isError: true,
                };
              }
              await persistCompletedAIRecord(aiRecord, "applied");
              setAxesData(updatedAxes);
              setInstruction(parsedInstruction);

              // Keep the model's machine-readable instruction internal. The
              // Timeline executes it through the instruction state above,
              // while the chat shows the concise confirmation used by the demo.
              return { text: "Done", assistantMode, aiRecord };
          }

          await persistCompletedAIRecord(aiRecord, "replied");
          return {
            text: normalMessage || responseString,
            assistantMode,
            aiRecord,
          };
        }

        await persistCompletedAIRecord(aiRecord, "replied");
        return { text: responseString, assistantMode, aiRecord };
      })
      .catch((error) => {
        console.error("Error in GPT API call:", error);
        return {
          text: error.message || "The AI assistant could not complete the request.",
          assistantMode: error.assistantMode ?? assistantRouting.mode,
          isError: true,
          canFallbackToRemote: error.canFallbackToRemote,
          canFallbackToLocal: error.canFallbackToLocal,
        } as AssistantReply;
      });
  };
  



  const handleSaveBooklist = (jsonData) => {
    
    if (!bookListFileName) {
      bookListFileName = `booklist_${new Date().getTime()}.json`;
    }
  
    console.log("BookList File Name: ", bookListFileName);
    console.log("Data to send: ", { name: bookListFileName, data: jsonData });
  
    fetch("http://localhost:8000/api/update_booklist/", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: bookListFileName, data: jsonData }),
    })
      .then((response) => {
        if (!response.ok) {
          throw new Error("Failed to save data");
        }
        return response.json();
      })
      .then((data) => {
        console.log("Success:", data);
        alert("Data saved successfully!");
        setEditMode(false);
        setBookList(jsonData);
        console.log("Updated BookList: ", bookListData);
      })
      .catch((error) => {
        console.error("Error:", error);
        alert("Failed to save data.");
      });
  };
  

  const handleOnEdit = () => {
    setEditMode(true);
  };

  const playerRef = useCallback((playerInstance: ReactPlayer | null) => {
    setPlayer(playerInstance);
  }, []);

  const handleSeek = useCallback((time: number) => {
    setPlayed(time);
    if (player) {
      player.seekTo(time, 'seconds');
    }
  }, [player]);

  const formatChunkTime = (seconds: number) => {
    const minutes = Math.floor(seconds / 60);
    const remainingSeconds = Math.floor(seconds % 60);
    return `${minutes}:${String(remainingSeconds).padStart(2, "0")}`;
  };

  const currentChunk = chunkManifest?.chunks?.[currentChunkIndex];
  const handleChunkSelection = (index: number | null | undefined) => {
    if (
      switchingChunk ||
      processingPending ||
      confirmingChunkSwitch ||
      index == null ||
      index === currentChunkIndex ||
      !chunkManifest?.chunks.some((chunk) => chunk.index === index)
    ) return;
    setChunkSwitchError("");
    setPendingChunkIndex(index);
  };

  const confirmChunkSelection = async () => {
    if (pendingChunkIndex === null || confirmingChunkSwitch) return;
    setConfirmingChunkSwitch(true);
    setChunkSwitchError("");
    try {
      await handleClearConversation();
      const targetIndex = pendingChunkIndex;
      setPendingChunkIndex(null);
      await onChunkChange(targetIndex);
    } catch {
      setChunkSwitchError("Could not clear the conversation. The chunk was not changed. Please try again.");
    } finally {
      setConfirmingChunkSwitch(false);
    }
  };

  return (
<AxesProvider
  key={chunkManifest ? `chunk-${currentChunkIndex}` : "whole-input"}
>
  <Dialog
    open={pendingChunkIndex !== null}
    onClose={() => !confirmingChunkSwitch && setPendingChunkIndex(null)}
  >
    <DialogTitle>Switch to chunk {pendingChunkIndex === null ? "" : pendingChunkIndex + 1}?</DialogTitle>
    <DialogContent>
      <DialogContentText>
        Your annotations will be saved and preserved, but the AI conversation history will be lost when you switch chunks.
      </DialogContentText>
      {chunkSwitchError && <DialogContentText color="error">{chunkSwitchError}</DialogContentText>}
    </DialogContent>
    <DialogActions>
      <Button disabled={confirmingChunkSwitch} onClick={() => setPendingChunkIndex(null)}>Cancel</Button>
      <Button disabled={confirmingChunkSwitch} onClick={confirmChunkSelection} variant="contained">
        Switch chunk
      </Button>
    </DialogActions>
  </Dialog>
  <Dialog
    open={pendingAIChange !== null}
    onClose={() => resolveAIChangeConfirmation(false)}
  >
    <DialogTitle>Allow AI timeline changes?</DialogTitle>
    <DialogContent>
      <DialogContentText>
        The AI instruction will delete or modify existing annotation
        timelines or blocks. Do you want to apply these changes?
      </DialogContentText>
    </DialogContent>
    <DialogActions>
      <Button onClick={() => resolveAIChangeConfirmation(false)}>
        Cancel
      </Button>
      <Button
        onClick={() => resolveAIChangeConfirmation(true)}
        color="error"
        variant="contained"
      >
        Apply changes
      </Button>
    </DialogActions>
  </Dialog>

  <Box
    display="flex"
    flexDirection="column"
    height="100vh"
    overflow="hidden"
  >
    <AppHeader
      rosBagFileName={rosBagFileName}
      disabled={processingPending}
      onSave={() => openSaveDialog.current?.()}
    />

    <Box display="flex" flex={1} minHeight={0} overflow="hidden">
        <Box
          display="flex"
          justifyContent="center"
          alignItems="center"
          flexDirection="column"
          flex={0.7}
          height="100%"  
          overflow="auto"
        >
          <Box display="flex" alignItems="center" gap={2} px={2} width="100%" boxSizing="border-box">
            <Button disabled={duration <= 0} onClick={() => {
              if (!isPlaying && played >= duration) handleSeek(0);
              setIsPlaying(value => !value);
            }}>{isPlaying ? 'Pause' : 'Play'}</Button>
            <Slider aria-label="Shared playback time" min={0} max={Math.max(duration, 0.001)} step={0.01}
              value={Math.min(played, duration)} onChange={(_, value) => handleSeek(value as number)} />
            <Typography variant="caption" whiteSpace="nowrap">{played.toFixed(2)} / {duration.toFixed(2)}s</Typography>
          </Box>
          <FrontEndWorkspace
            context={{
              videoPath: data.video_path,
              audioPath: data.audio_path,
              waveformPath: data.waveform_image_path,
              views: data.views,
              transcript: data.audio_transcript,
              played,
              isPlaying,
              onProgress: setPlayed,
              onPlay: () => setIsPlaying(true),
              onPause: () => setIsPlaying(false),
              onSeek: handleSeek,
              onDurationChange: setDuration,
              playerRef,
            }}
          />
  

          {chunkManifest?.chunking_enabled && (
            <Paper
              elevation={1}
              sx={{
                width: "calc(100% - 16px)",
                maxWidth: 1200,
                mx: 1,
                mb: 1,
                px: 1.5,
                py: 1,
                display: "grid",
                gridTemplateColumns: "1fr auto 1fr",
                alignItems: "center",
                gap: 2,
              }}
            >
              <Button
                variant="outlined"
                onClick={() => handleChunkSelection(currentChunk?.previous_index)}
                disabled={switchingChunk || processingPending || confirmingChunkSwitch || currentChunk?.previous_index == null}
                sx={{ justifySelf: "start" }}
              >
                ← Previous
              </Button>

              <Box display="flex" alignItems="center" gap={1.5}>
                <Typography fontWeight={600}>Chunk</Typography>
                <FormControl size="small" sx={{ minWidth: 210 }}>
                  <Select
                    value={currentChunkIndex}
                    onChange={(event) => handleChunkSelection(Number(event.target.value))}
                    disabled={switchingChunk || processingPending || confirmingChunkSwitch}
                    aria-label="Select video chunk"
                  >
                    {chunkManifest.chunks.map((chunk) => (
                      <MenuItem key={chunk.index} value={chunk.index}>
                        {`Chunk ${chunk.index + 1} · ${formatChunkTime(chunk.start_seconds)}–${formatChunkTime(chunk.end_seconds)}`}
                      </MenuItem>
                    ))}
                  </Select>
                </FormControl>
                {switchingChunk && <CircularProgress size={22} />}
                <Typography color="text.secondary" whiteSpace="nowrap">
                  {`${currentChunkIndex + 1} / ${chunkManifest.chunk_count}`}
                </Typography>
              </Box>

              <Button
                variant="outlined"
                onClick={() => handleChunkSelection(currentChunk?.next_index)}
                disabled={switchingChunk || processingPending || confirmingChunkSwitch || currentChunk?.next_index == null}
                sx={{ justifySelf: "end" }}
              >
                Next →
              </Button>
            </Paper>
          )}

          <Box width="100%" maxWidth={1200} overflow="auto" maxHeight="30vh">
            {processingPending ? <Typography>Preparing annotation data?</Typography> : <Timeline
              key={chunkManifest ? `chunk-${currentChunkIndex}` : "whole-input"}
              rosBagFileName={rosBagFileName}
              bookListFileName={bookListFileName}
              duration={duration}
              sourceDuration={sourceDuration}
              played={played}
              onSeek={handleSeek}
              booklist={bookList}
              annotationData={data.annotation_data}
              speakerData={data.speaker_data}
              onAxesUpdate={handleAxesUpdate}
              instruction={instruction}
              restoredAxes={restoredAxes}
              autosaveEnabled={autosaveEnabled}
              autosaveScope={chunkManifest?.chunking_enabled ? {
                manifest_id: chunkManifest.id,
                chunk_index: currentChunkIndex,
              } : undefined}
              onAutosaveReady={onAutosaveReady}
              savedAnnotationName={savedAnnotationName}
              onAnnotationSaved={onAnnotationSaved}
              switchingChunk={switchingChunk}
              aiRecords={aiRecords}
              onSaveReady={registerSaveDialog}
            />}
          </Box>
        </Box>
  

        <RightAssistantPanel
          onClearConversation={handleClearConversation}
          codebook={
            editMode ? (
              <EditBooklistForm
                bookListData={bookList}
                onSave={handleSaveBooklist}
              />
            ) : (
              <Box padding={2}>
                <Button onClick={handleOnEdit} disabled={processingPending} variant="contained">
                  Edit
                </Button>
                <Booklist bookListData={bookList} />
              </Box>
            )
          }
          assistant={<Chatbox key={conversationKey} onSendMessage={handleSendMessageToGPT} />}
        />
        </Box>
      </Box>
    </AxesProvider>
  );
};

export default Annotator;
