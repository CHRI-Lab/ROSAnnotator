import { useEffect, useState } from "react";
import { Alert, Box, Button, Dialog, DialogActions, DialogContent, DialogContentText, DialogTitle, MenuItem, Pagination, TextField, Typography } from "@mui/material";
import type { SpeakerSegment } from "../../types/annotations";
import { createTranscriptDraft, parseTranscriptDraft, renameTranscriptSpeaker, type TranscriptDraft } from "./transcriptDraft";

interface TranscriptEditorProps {
  segments: SpeakerSegment[];
  duration: number;
  chunked: boolean;
  onSave: (segments: SpeakerSegment[]) => Promise<void>;
  onClose: () => void;
}

const PAGE_SIZE = 20;

export default function TranscriptEditor({ segments, duration, chunked, onSave, onClose }: TranscriptEditorProps) {
  const [draft, setDraft] = useState(() => createTranscriptDraft(segments));
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [page, setPage] = useState(1);
  const [renameFrom, setRenameFrom] = useState(segments[0]?.speaker_label.trim() || "");
  const [renameTo, setRenameTo] = useState("");
  const dirty = JSON.stringify(draft) !== JSON.stringify(createTranscriptDraft(segments));
  const speakers = [...new Set(draft.map(segment => segment.speaker_label.trim()).filter(Boolean))];
  const pageCount = Math.max(1, Math.ceil(draft.length / PAGE_SIZE));
  const currentPage = Math.min(page, pageCount);
  const first = (currentPage - 1) * PAGE_SIZE;

  useEffect(() => {
    if (!dirty) return;
    const beforeUnload = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = ""; };
    window.addEventListener("beforeunload", beforeUnload);
    return () => window.removeEventListener("beforeunload", beforeUnload);
  }, [dirty]);

  const updateSegment = (index: number, patch: Partial<TranscriptDraft>) =>
    setDraft(current => current.map((segment, i) => i === index ? { ...segment, ...patch } : segment));

  const save = async () => {
    if (saving) return;
    setError("");
    try {
      const parsed = parseTranscriptDraft(draft, duration);
      setSaving(true);
      await onSave(parsed);
      setSaving(false);
      onClose();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Unable to save the transcript. Please retry.");
      setSaving(false);
    }
  };

  return (
    <Dialog open fullWidth maxWidth="lg" onClose={() => { if (!dirty && !saving) onClose(); }} disableEscapeKeyDown={dirty || saving}>
      <DialogTitle>Edit transcript</DialogTitle>
      <DialogContent>
        <DialogContentText sx={{ mb: 2 }}>
          Times are seconds from the start of {chunked ? "this chunk" : "the input"} (0–{duration}s).
          Saved changes are used for transcript display, AI requests, and new annotation conversion.
          Existing annotation blocks are kept as they are.
        </DialogContentText>
        {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}
        <Box display="flex" flexWrap="wrap" gap={1} alignItems="center" mb={2}>
          <TextField select label="Rename speaker" size="small" sx={{ minWidth: 180 }} disabled={saving || !speakers.length}
            value={speakers.includes(renameFrom) ? renameFrom : ""} onChange={event => setRenameFrom(event.target.value)}>
            {speakers.map(speaker => <MenuItem key={speaker} value={speaker}>{speaker}</MenuItem>)}
          </TextField>
          <TextField label="New speaker label" size="small" value={renameTo} disabled={saving} onChange={event => setRenameTo(event.target.value)} />
          <Button disabled={saving || !speakers.includes(renameFrom) || !renameTo.trim() || /[\r\n]/.test(renameTo)} onClick={() => {
            setDraft(current => renameTranscriptSpeaker(current, renameFrom, renameTo));
            setRenameFrom(renameTo.trim());
            setRenameTo("");
          }}>Rename all matching segments</Button>
        </Box>
        {!draft.length && <Typography sx={{ mb: 2 }}>The transcript is empty. Add a segment to start.</Typography>}
        {draft.slice(first, first + PAGE_SIZE).map((segment, offset) => {
          const index = first + offset;
          return <Box key={index} sx={{ border: 1, borderColor: "divider", borderRadius: 1, p: 2, mb: 2 }}>
            <Box display="flex" flexWrap="wrap" gap={1} alignItems="center" mb={1}>
              <Typography>#{index + 1}</Typography>
              <TextField label="Speaker" size="small" value={segment.speaker_label} disabled={saving}
                onChange={event => updateSegment(index, { speaker_label: event.target.value })} />
              <TextField label="Start (seconds)" size="small" type="number" sx={{ width: 160 }} value={segment.start_time} disabled={saving}
                inputProps={{ min: 0, max: duration, step: "any" }} onChange={event => updateSegment(index, { start_time: event.target.value })} />
              <TextField label="End (seconds)" size="small" type="number" sx={{ width: 160 }} value={segment.end_time} disabled={saving}
                inputProps={{ min: 0, max: duration, step: "any" }} onChange={event => updateSegment(index, { end_time: event.target.value })} />
              <Button color="error" disabled={saving} onClick={() => setDraft(current => current.filter((_, i) => i !== index))}>Remove segment</Button>
            </Box>
            <TextField label="Transcript text" fullWidth multiline minRows={2} value={segment.text} disabled={saving}
              onChange={event => updateSegment(index, { text: event.target.value })} />
          </Box>;
        })}
        <Box display="flex" flexWrap="wrap" gap={2} justifyContent="space-between" alignItems="center">
          <Button disabled={saving} onClick={() => {
            const start = Math.max(0, Math.min(duration, Number(draft[draft.length - 1]?.end_time) || 0));
            setDraft(current => [...current, { speaker_label: speakers[0] || "Speaker", text: "", start_time: String(start), end_time: String(Math.min(duration, start + 1)) }]);
            setPage(Math.ceil((draft.length + 1) / PAGE_SIZE));
          }}>Add segment</Button>
          <Pagination count={pageCount} page={currentPage} disabled={saving} onChange={(_, value) => setPage(value)} />
        </Box>
      </DialogContent>
      <DialogActions>
        <Button disabled={saving} onClick={onClose}>Cancel</Button>
        <Button variant="contained" disabled={saving || !dirty} onClick={save}>{saving ? "Saving…" : "Save transcript"}</Button>
      </DialogActions>
    </Dialog>
  );
}
