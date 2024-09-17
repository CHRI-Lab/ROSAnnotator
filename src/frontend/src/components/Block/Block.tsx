import React, { useState, useEffect, useRef } from 'react';
import { TextField, styled, IconButton, MenuItem, Tooltip, Select as MuiSelect } from '@mui/material';

const CustomSelect = styled(MuiSelect)(({ theme }) => ({
  '& .MuiOutlinedInput-notchedOutline': {
    border: 'none',
  },
  '&.Mui-focused .MuiOutlinedInput-notchedOutline': {
    border: 'none',
  },
  '& .MuiSelect-select': {
    padding: theme.spacing(1),
  },
  '& .MuiInputBase-root': {
    '&:hover:not(.Mui-disabled):before': {
      borderBottom: 'none',
    },
    '&:before': {
      borderBottom: 'none',
    },
  },
}));

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
  })
);

const Block: React.FC<BlockProps> = ({ block, duration, axisType, booklist, onSave, onDelete }) => {
  const [isEditing, setIsEditing] = useState(false);
  const [selectedAnnotation, setSelectedAnnotation] = useState(block.text || '');
  const [start, setStart] = useState(block.start);
  const [end, setEnd] = useState(block.end);
  const containerRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    setSelectedAnnotation(block.text || '');
    setStart(block.start);
    setEnd(block.end);
  }, [block.text, block.start, block.end]);

  const handleDoubleClick = () => {
    setIsEditing(true);
  };

  const handleSave = () => {
    onSave(selectedAnnotation, start, end);
    setIsEditing(false);
  };

  const handleSelectChange = (event: any) => {
    setSelectedAnnotation(event.target.value as string);
  };

  const handleBlur = (e: React.FocusEvent<HTMLDivElement>) => {
    if (!containerRef.current?.contains(e.relatedTarget)) {
      handleSave();
    }
  };

  return (
    <Tooltip title={`${selectedAnnotation} (${start} - ${end})`} placement="top" arrow>
      <BlockDisplay
        start={start}  // Use state start here
        end={end}      // Use state end here
        duration={duration}
        onDoubleClick={handleDoubleClick}
      >
        {isEditing ? (
          <div 
          ref={containerRef} 
          tabIndex={-1} 
          onBlur={handleBlur} 
          style={{ display: 'flex', alignItems: 'center', gap: '10px' }}  // Added flexbox layout
        >
            <TextField
              value={selectedAnnotation}
              onChange={(e) => setSelectedAnnotation(e.target.value)}
              autoFocus
              fullWidth
            />
            <TextField
              label="Start"
              type="number"
              value={start}
              onChange={(e) => setStart(parseFloat(e.target.value, 10))}
              inputProps={{
                size: start.toString().length || 1, // Dynamically adjust size based on length
                min: 0,  // Ensure valid input
                style: { minWidth: '50px' },  // Set a minimum width
                step:0.001
              }}
            />
            <TextField
              label="End"
              type="number"
              value={end}
              onChange={(e) => setEnd(parseFloat(e.target.value, 10))}
              inputProps={{
                size: end.toString().length || 1, // Dynamically adjust size based on length
                min: 0,  // Ensure valid input
                style: { minWidth: '50px' },  // Set a minimum width
                step:0.001
              }}
            />
          </div>
        ) : axisType === 'selected' ? (
          <CustomSelect
            value={selectedAnnotation}
            onChange={handleSelectChange}
            displayEmpty
            fullWidth
          >
            {booklist.map((annotation) => (
              <MenuItem key={annotation} value={annotation}>
                {annotation}
              </MenuItem>
            ))}
          </CustomSelect>
        ) : (
          <span>{`${selectedAnnotation} (${start} - ${end})`}</span>
        )}
        <IconButton onClick={onDelete} size="small">
          x
        </IconButton>
      </BlockDisplay>
    </Tooltip>
  );
};

export default Block;
