import React, { useState, useEffect } from 'react';
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
      borderBottom: 'none'  
    },
    '&:before': {
      borderBottom: 'none'  
    }
  }
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
  onSave: (text: string) => void;
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

  useEffect(() => {
    setSelectedAnnotation(block.text || '');
  }, [block.text]);

  const handleDoubleClick = () => {
      setIsEditing(true);
  };

  const handleBlur = () => {
    onSave(selectedAnnotation);
    setIsEditing(false);
  };

  const handleSelectChange = (event: any) => {
    setSelectedAnnotation(event.target.value as string);
    onSave(event.target.value as string);
  };

  return (
    <Tooltip title={selectedAnnotation} placement="top" arrow>
      <BlockDisplay
        start={block.start}
        end={block.end}
        duration={duration}
        onDoubleClick={handleDoubleClick}
      >
        { isEditing ? (
          <TextField
            value={selectedAnnotation}
            onChange={(e) => setSelectedAnnotation(e.target.value)}
            onBlur={handleBlur}
            autoFocus
            fullWidth
          />
        ) : axisType === 'selected' ? (
          <CustomSelect
            value={selectedAnnotation}
            onChange={handleSelectChange}
            displayEmpty
            fullWidth
          >
            {booklist.map(annotation => (
              <MenuItem key={annotation} value={annotation}>{annotation}</MenuItem>
            ))}
          </CustomSelect>
        ) : (
          <span>{selectedAnnotation || 'Double-click to edit'}</span>
        )}
        <IconButton onClick={onDelete} size="small">
          x
        </IconButton>
      </BlockDisplay>
    </Tooltip>
  );
};

export default Block;
