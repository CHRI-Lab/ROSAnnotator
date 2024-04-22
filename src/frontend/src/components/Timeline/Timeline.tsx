import React, { useState, useEffect } from 'react';
import { Button, Dialog, DialogTitle, DialogActions } from '@mui/material';
import Box from '@mui/material/Box';
import Slider from '@mui/material/Slider';
import { styled } from '@mui/system';
import CustomSnackbar from '../CustomSnackbar'; // 引入新的 Snackbar 组件

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
  backgroundColor: '#ddd', // 新轴的背景颜色
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
  const [dialogOpen, setDialogOpen] = useState(false);
  const [snackbarOpen, setSnackbarOpen] = useState(false);

  useEffect(() => {
    setSeekTime(played);
  }, [played]);

  const handleSliderChange = (event: Event, newValue: number | number[]) => {
    setSeekTime(newValue as number);
    onSeek(newValue as number);
  };

  const handleRangeChange = (event: Event, newValue: number | number[]) => {
    setSelectedRange(newValue as number[]);
  };

  const handleCreateBlock = () => {
    const isOverlap = blocks.some(block =>
      selectedRange[0] < block.end && selectedRange[1] > block.start
    );
    if (isOverlap) {
      // 如果有重叠，打开警告弹窗
      setDialogOpen(true);
    } else {
      // 否则，添加新的block
      const newBlock = { start: selectedRange[0], end: selectedRange[1] };
      setBlocks(prevBlocks => [...prevBlocks, newBlock]);
      setSnackbarOpen(true);
    }
  };

  const handleSnackbarClose = () => {
    setSnackbarOpen(false); // 关闭 Snackbar
  };

  const handleCloseDialog = () => {
    setDialogOpen(false);
  };

  const selectBlock = (index: number) => {
    setSelectedBlockIndex(index); // 设置选中的block的索引
  };

  const deleteSelectedBlock = () => {
    if (selectedBlockIndex !== null) {
      setBlocks(blocks => blocks.filter((_, index) => index !== selectedBlockIndex));
      setSelectedBlockIndex(null); // 删除后清除选中状态
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
      <Dialog open={dialogOpen} onClose={handleCloseDialog}>
        <DialogTitle>Duplicate Annotations</DialogTitle>
        <DialogActions>
          <Button onClick={handleCloseDialog}>OK</Button>
        </DialogActions>
      </Dialog>
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
              position: 'absolute', // 与时间轴对齐
              left: 0, // 确保从容器的最左侧开始
              right: 0, // 确保延伸到容器的最右侧
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
                width: `${((block.end - block.start) / duration) * 100}%`,
                backgroundColor: selectedBlockIndex === index ? 'red' : 'grey',
              }}
            />
          ))}
        </NewAxisArea>
        {selectedBlockIndex !== null && (
          <Button onClick={deleteSelectedBlock} variant="contained" color="secondary">
            Delete Block
          </Button>
        )}
        {selectedBlockIndex === null && (
         <Button onClick={handleCreateBlock} variant="contained" color="primary" >
           Create Block
         </Button>
        )}
        {selectedBlockIndex !== null && (
          <Button onClick={() => setSelectedBlockIndex(null)} variant="outlined" color="inherit">
           Cancel
          </Button>
        )}
      </ScrollableTimelineContainer>
    </Box>
  );
};

export default Timeline;
