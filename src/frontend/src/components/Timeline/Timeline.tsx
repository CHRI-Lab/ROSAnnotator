import React, { useState, useEffect } from 'react';
import { Button} from '@mui/material';
import Box from '@mui/material/Box';
import Slider from '@mui/material/Slider';
import { styled } from '@mui/system';
import CustomSnackbar from '../CustomSnackbar';

interface TimelineProps {
  duration: number;
  played: number;
  onSeek: (time: number) => void;
  markInterval: number;
}
interface Block {
  start: number;
  end: number;
}
const ScrollableTimelineContainer = styled('div')({
  overflowX: 'scroll',
  overflowY: 'hidden',
  width: '100%',
  cursor: 'pointer',
  padding: '10px 0',
});

const TimelineMarks = styled('div')({
  position: 'relative',
  display: 'flex',
  alignItems: 'center',
  height: '10px',
});

const TimelineMarkLabel = styled('div')(({ theme }) => ({
  position: 'absolute',
  color: theme.palette.text.primary,
  fontSize: '0.75rem',
  transform: 'translateX(-50%)',
  userSelect: 'none',
}));

const SelectionArea = styled('div')(({ theme }) => ({
  position: 'relative',
  height: '20px',
  marginTop: '5px',
  backgroundColor: theme.palette.action.selected,
}));

const NewAxisArea = styled('div')({
  position: 'relative',
  height: '50px',
  marginTop: '10px',
  marginBottom: '10px',
  backgroundColor: '#ddd', 
});

const NewBlock = styled('div')(({ theme }) => ({
  position: 'absolute',
  height: '100%',
  backgroundColor: theme.palette.action.selected,
}));


const Timeline: React.FC<TimelineProps> = ({ duration, played, onSeek, markInterval }) => {
  const [seekTime, setSeekTime] = useState(played);
  const [selectedRange, setSelectedRange] = useState<number[]>([0, 1]);
  const [blocks, setBlocks] = useState<Block[]>([]);
  const [selectedBlockIndex, setSelectedBlockIndex] = useState<number | null>(null);
  const [snackbarOpen, setSnackbarOpen] = useState(false);

  useEffect(() => {
    setSeekTime(played);
  }, [played]);

  const handleSliderChange = (_event: Event, newValue: number | number[]) => {
    setSeekTime(newValue as number);
    onSeek(newValue as number);
  };

  const handleRangeChange = (_event: Event, newValue: number | number[]) => {
    setSelectedRange(newValue as number[]);
  };

  const handleCreateBlock = () => {
    const newBlock = { start: selectedRange[0], end: selectedRange[1] };
    setBlocks(prevBlocks => [...prevBlocks, newBlock]);
    setSnackbarOpen(true);

  };

  const handleSnackbarClose = () => {
    setSnackbarOpen(false);
  };

  const selectBlock = (index: number) => {
    setSelectedBlockIndex(index); 
  };

  const deleteSelectedBlock = () => {
    if (selectedBlockIndex !== null) {
      setBlocks(blocks => blocks.filter((_, index) => index !== selectedBlockIndex));
      setSelectedBlockIndex(null); 
    }
  };

  const marks = Array.from(
    { length: Math.ceil(duration / markInterval) },
    (_, index) => ({
      value: markInterval * index,
      label: `${markInterval * index}s`,
    })
  );

  const totalWidth = duration / markInterval * 50;

  return (
    <Box  sx={{ margin: '20px 0' }}>
      <CustomSnackbar
        open={snackbarOpen}
        message="Block created"
        handleClose={handleSnackbarClose}
      />
      <ScrollableTimelineContainer>
        <Slider
          value={seekTime}
          min={0}
          max={duration}
          step={0.01}
          onChange={handleSliderChange}
          valueLabelDisplay="off"
          marks={marks.map(mark => ({ value: mark.value, label: '' }))}
          sx={{
            width: `${totalWidth}px`,
            '& .MuiSlider-track': { backgroundColor: 'transparent' },
            '& .MuiSlider-thumb': {
              width: '20px',
              height: '20px',
              marginTop: '0px',
              '&:before': { boxShadow: '0 4px 8px rgba(0,0,0,0.4)' },
            },
            '& .MuiSlider-rail': { height: '8px', opacity: 0.5 },
          }}
        />
        <TimelineMarks style={{ width: `${totalWidth}px` }}>
          {marks.map((mark, index) => (
            <TimelineMarkLabel
              key={index}
              style={{ left: `${(mark.value / duration) * 100}%` }}
            >
              {mark.label}
            </TimelineMarkLabel>
          ))}
        </TimelineMarks>
        <SelectionArea style={{ width: `${totalWidth}px` }}>
          <Slider
            value={selectedRange}
            onChange={handleRangeChange}
            valueLabelDisplay="auto"
            min={0}
            max={duration}
            step={1}
            sx={{
              position: 'absolute', 
              left: 0, 
              right: 0, 
              '& .MuiSlider-thumb': {
                backgroundColor: 'primary.main',
              },
            }}
            disableSwap
          />
        </SelectionArea>
        <NewAxisArea style={{ width: `${totalWidth}px` }}>
          {blocks.map((block, index) => (
            <NewBlock
              key={index}
              onClick={() => selectBlock(index)}
              style={{
                left: `${(block.start / duration) * 100}%`,
                width: `max(${5}px,${((block.end - block.start) / duration) * 100}%)`,
                backgroundColor: selectedBlockIndex === index ? 'red' : 'grey',
              }}
            />
          ))}
        </NewAxisArea>
      </ScrollableTimelineContainer>
      <Box sx={{ display: 'flex', justifyContent: 'center', gap: 2, mt: 2 }}>
          {selectedBlockIndex === null && (
            <Button onClick={handleCreateBlock} variant="contained" color="primary">
              Create Anotation Block
           </Button>
         )}
         {selectedBlockIndex !== null && (
            <>
             <Button onClick={deleteSelectedBlock} variant="contained" color="secondary">
                Delete
             </Button>
             <Button onClick={() => setSelectedBlockIndex(null)} variant="outlined">
                Cancel
              </Button>
            </> 
         )}
    </Box>
    </Box>
  );
};

export default Timeline;
