import React, { useState, useEffect } from 'react';
import { Box, Button, TextField, styled, IconButton, MenuItem, Popover, Tooltip } from '@mui/material';
import { clampTimeToDuration } from '../Timeline/blockBounds';

interface BlockProps {
  block: {
    start: number;
    end: number;
    text?: string;
  };
  duration: number;
  axisType: string;
  booklist: string[];
  onSave: (text: string, start: number, end: number) => void;
  onDelete: () => void;
}

const BlockDisplay = styled('div')<{ start: number; end: number; duration: number }>(
  ({ theme, start, end, duration }) => ({
    position: 'absolute',
    left: `${(start / duration) * 100}%`,
    top: '50%',
    transform: 'translateY(-50%)',
    width: `${((end - start) / duration) * 100}%`,
    height: '80%',
    backgroundColor: theme.palette.action.selected,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    cursor: 'pointer',
    border: '1px solid black',
    boxSizing: 'border-box',
    padding: '0 10px',
    overflow: 'hidden',
  })
);

const BlockText = styled('span')({
  flex: '1 1 auto',
  minWidth: 0,
  maxHeight: '100%',
  overflow: 'hidden',
  whiteSpace: 'normal',
  overflowWrap: 'anywhere',
  wordBreak: 'break-word',
  lineHeight: 1.2,
});

const Block: React.FC<BlockProps> = ({ block, duration, axisType, booklist, onSave, onDelete }) => {
  
  const [isEditing, setIsEditing] = useState(false);
  const [selectedAnnotation, setSelectedAnnotation] = useState(block.text || '');
  const [start, setStart] = useState(block.start);
  const [end, setEnd] = useState(block.end);
  const [editorAnchor, setEditorAnchor] = useState<HTMLElement | null>(null);
  const [tooltipOpen, setTooltipOpen] = useState(false);
  const [updatedBooklist, setUpdatedBooklist] = useState<string[]>([]);

  useEffect(() => {
    if (booklist && Array.isArray(booklist)) {
      // 更新 booklist，确保它为有效数组
      setUpdatedBooklist(booklist.length > 0 ? booklist : ['Default annotation']);
    } else {
      // 如果 booklist 不存在，设置默认值
      setUpdatedBooklist(['Default annotation']);
    }
  }, [booklist]);

  useEffect(() => {
    setSelectedAnnotation(block.text || '');
    setStart(block.start);
    setEnd(block.end);
  }, [block.text, block.start, block.end]);

  const handleClick = (event: React.MouseEvent<HTMLDivElement>) => {
    setTooltipOpen(false);
    setEditorAnchor(event.currentTarget);
    setIsEditing(true);
  };

  const handleSave = () => {
    onSave(selectedAnnotation, start, end);
    setIsEditing(false);
    setEditorAnchor(null);
  };

  const handleCancel = () => {
    setSelectedAnnotation(block.text || '');
    setStart(block.start);
    setEnd(block.end);
    setIsEditing(false);
    setEditorAnchor(null);
  };

  const invalidRange = !Number.isFinite(start)
    || !Number.isFinite(end)
    || start < 0
    || end < start
    || end > duration;

  return (
    <>
      <Tooltip
        title={`${selectedAnnotation} (${start} - ${end})`}
        placement="top"
        arrow
        open={tooltipOpen && !isEditing}
        onOpen={() => {
          if (!isEditing) setTooltipOpen(true);
        }}
        onClose={() => setTooltipOpen(false)}
        disableHoverListener={isEditing}
      >
        <BlockDisplay
          start={start}
          end={end}
          duration={duration}
          onClick={handleClick}
        >
          <BlockText>{`${selectedAnnotation} (${start} - ${end})`}</BlockText>
          <IconButton
            onClick={(event) => {
              event.stopPropagation();
              onDelete();
            }}
            size="small"
            aria-label="Delete annotation block"
            sx={{ flexShrink: 0 }}
          >
            x
          </IconButton>
        </BlockDisplay>
      </Tooltip>

      <Popover
        open={isEditing}
        anchorEl={editorAnchor}
        onClose={handleCancel}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }}
        transformOrigin={{ vertical: 'top', horizontal: 'center' }}
      >
        <Box
          display="flex"
          flexDirection="column"
          gap={1.5}
          width="min(400px, calc(100vw - 24px))"
          p={1.5}
          boxSizing="border-box"
        >
          <Box component="strong">Edit annotation block</Box>
          {axisType === 'selected' ? (
            <TextField
              select
              label="Annotation"
              value={selectedAnnotation}
              onChange={(event) => setSelectedAnnotation(event.target.value)}
              autoFocus
              fullWidth
            >
              {updatedBooklist.map((annotation) => (
                <MenuItem key={annotation} value={annotation}>
                  {annotation}
                </MenuItem>
              ))}
            </TextField>
          ) : (
            <TextField
              label="Annotation"
              value={selectedAnnotation}
              onChange={(event) => setSelectedAnnotation(event.target.value)}
              autoFocus
              multiline
              minRows={2}
              fullWidth
            />
          )}
          <Box display="flex" gap={1.5}>
            <TextField
              label="Start time (seconds)"
              type="number"
              value={start}
              onChange={(event) => setStart(
                clampTimeToDuration(parseFloat(event.target.value), duration)
              )}
              inputProps={{ min: 0, max: duration, step: 0.001 }}
              fullWidth
            />
            <TextField
              label="End time (seconds)"
              type="number"
              value={end}
              onChange={(event) => setEnd(
                clampTimeToDuration(parseFloat(event.target.value), duration)
              )}
              inputProps={{ min: 0, max: duration, step: 0.001 }}
              fullWidth
            />
          </Box>
          <Box display="flex" justifyContent="flex-end" gap={1}>
            <Button onClick={handleCancel}>Cancel</Button>
            <Button onClick={handleSave} disabled={invalidRange} variant="contained">
              Save
            </Button>
          </Box>
        </Box>
      </Popover>
    </>
  );
};

export default Block;
