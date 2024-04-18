import React, { useState, useEffect } from 'react';
import Box from '@mui/material/Box';
import Slider from '@mui/material/Slider';
import { styled } from '@mui/system';

interface TimelineProps {
  duration: number; // 视频总时长
  played: number; // 当前播放时间
  onSeek: (time: number) => void; // 跳转函数
  markInterval: number; // 刻度间隔
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

const Timeline: React.FC<TimelineProps> = ({ duration, played, onSeek, markInterval }) => {
  const [seekTime, setSeekTime] = useState(played);
  
  useEffect(() => {
    setSeekTime(played);
  }, [played]);

  const handleSliderChange = (event: Event, newValue: number | number[]) => {
    setSeekTime(newValue as number);
    onSeek(newValue as number);
  };

  const marks = Array.from(
    { length: Math.ceil(duration / markInterval) }, 
    (_, index) => ({
      value: markInterval * index,
      label: `${markInterval * index}s`,
    })
  );

  // 计算整个时间轴的宽度，可以根据需要调整
  const totalWidth = duration / markInterval * 50; // 每个间隔50px

  return (
    <Box sx={{ margin: '20px 0' }}>
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
            width: `${totalWidth}px`, // 使用计算出的总宽度
            '& .MuiSlider-track': { backgroundColor: 'transparent' },
            '& .MuiSlider-thumb': {
              width: '20px',
              height: '20px',
              marginTop: '-6px',
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
      </ScrollableTimelineContainer>
    </Box>
  );
};

export default Timeline;
