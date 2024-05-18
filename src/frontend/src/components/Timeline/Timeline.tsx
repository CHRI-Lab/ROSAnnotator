  import React, { useState, useEffect } from 'react';
  import {Box, Button, Slider, Paper, Dialog, DialogTitle, DialogActions, DialogContent, DialogContentText, Typography } from '@mui/material';
  import { styled } from '@mui/system';
  import Axis from '../Axis';
  import AxisManager from '../AxisManager';

  let globalAxisId = 0;

  interface BlockProps {
    start: number;
    end: number;
    text?: string;
  }

  interface AxisData {
    id: number;
    type: string;
    typeName?: string;
    axisName?: string;
    shortcutKey?: string;
    blocks: BlockProps[];
  }

  interface TimelineProps {
    duration: number;
    played: number;
    onSeek: (time: number) => void;
    annotations: any;
  }

  const MainContainer = styled(Paper)(({ theme }) => ({
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    background: theme.palette.background.paper,
    boxShadow: '0px 1px 5px rgba(0,0,0,0.2)',
    padding: '20px',
    margin: '20px',
    width: 'auto'
  }));


  const ControlsContainer = styled('div')({
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: '20px',
    width: '100%'
  });

  const ScrollableTimelineContainer = styled('div')({
    overflowX: 'scroll',
    overflowY: 'hidden',
    width: '100%',
    padding: '10px 0',
    position: 'relative',
  });

  const ButtonsContainer = styled('div')({
    display: 'flex',
    flexDirection: 'column',
    padding: '10px',
    alignItems: 'flex-start'
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

  const Timeline: React.FC<TimelineProps> = ({ duration, played, onSeek, annotations }) => {
    const [seekTime, setSeekTime] = useState(played);
    const [markInterval, setMarkInterval] = useState(1);
    const [selectedRange, setSelectedRange] = useState<number[]>([0, 0.1 * duration]);
    const [axes, setAxes] = useState<AxisData[]>([]);
    const [isDialogOpen, setIsDialogOpen] = useState(false);
    const [error, setError] = useState("");
    const [isErrorDialogOpen, setIsErrorDialogOpen] = useState(false);

    useEffect(() => {
      const handleKeyPress = (event: KeyboardEvent) => {
        if (event.target instanceof HTMLElement && event.target.tagName === 'INPUT') {
          return;
        }

        const pressedKey = event.key;
        const targetedAxes = axes.filter(axis => axis.shortcutKey === pressedKey);
        targetedAxes.forEach(axis => {
          handleCreateBlock(axis.id);
        });
      };

      window.addEventListener('keydown', handleKeyPress);
      return () => {
        window.removeEventListener('keydown', handleKeyPress);
      };
    }, [axes, selectedRange]);

    const collectData = () => {
      const data = axes.map(axis => ({
        id: axis.id,
        type: axis.type,
        typeName: axis.typeName,
        blocks: axis.blocks.map(block => ({
          start: block.start,
          end: block.end,
          text: block.text
        }))
      }));
      console.log(data);
    };



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

    const handleAddAxis = () => {
      setAxes(prev => [...prev, { id: globalAxisId++, type: 'type-in', blocks: [] }]);
    };

    const handleCreateBlock = (axisId: number) => {
      const newBlock = { start: selectedRange[0], end: selectedRange[1], text: "" };

      // 检查是否有重叠
      const axis = axes.find(axis => axis.id === axisId);
      if (axis) {
        const overlap = axis.blocks.some(block =>
          (newBlock.start <= block.end && newBlock.end >= block.start)
        );

        if (overlap) {
          setError("Error: Block overlaps with an existing block. Create a new axis or adjust the range.");
          setIsErrorDialogOpen(true);
          return;
        }
      }

      setError("");
      setIsErrorDialogOpen(false);
      setAxes(prevAxes => prevAxes.map(axis => {
        if (axis.id === axisId) {
          const updatedBlocks = [...axis.blocks, newBlock];
          return { ...axis, blocks: updatedBlocks };
        }
        return axis;
      }));
    };

    const handleDeleteBlock = (axisId: number, blockIndex: number) => {
      setAxes(axes.map(axis => {
        if (axis.id === axisId) {
          const newBlocks = axis.blocks.filter((_, index) => index !== blockIndex);
          return { ...axis, blocks: newBlocks };
        }
        return axis;
      }));
    };

    const handleDeleteAxis = (axisId: number) => {
      setAxes(axes => axes.filter(axis => axis.id !== axisId));
    };

    const handleTypeChange = (axisId: number, type: string, typeName?: string) => {
      setAxes(axes => axes.map(axis => {
        if (axis.id === axisId) {
          return { ...axis, type, typeName };
        }
        return axis;
      }));
    };
    
    const handleNameChange = (axisId:number, axisName:string) => {
      setAxes(axes => axes.map(axis => {
        if (axis.id === axisId) {
          return { ...axis, axisName: axisName };
        }
        return axis;
      }));
    };
    
    const handleSave = (axisId: number, blockIndex: number, newText: string) => {
      setAxes(axes.map(axis => {
        if (axis.id === axisId) {
          const newBlocks = axis.blocks.map((block, index) => {
            if (index === blockIndex) {
              return { ...block, text: newText };
            }
            return block;
          });
          return { ...axis, blocks: newBlocks };
        }
        return axis;
      }));
    };

    

    const marks = Array.from({ length: Math.ceil(duration / markInterval) }, (_, index) => {
      const value = Math.round((markInterval * index) * 10) / 10; 
      return {
        value: value,
        label: `${value}s`,
      };
    });

    const handleShortcutChange = (axisId: number, shortcutKey: string) => {
      setAxes(axes => axes.map(axis => {
        if (axis.id === axisId) {
          return { ...axis, shortcutKey };  
        }
        return axis;
      }));
    };

    const handleMarkIntervalChange = (event: React.ChangeEvent<HTMLInputElement>) => {
      let newValue = parseFloat(event.target.value);

      if (isNaN(newValue)) {
        newValue = 1;
      } else {
        newValue = Math.round(newValue * 10) / 10;

        if (newValue < 0.1) {
          newValue = 0.1;
        }
      }

      setMarkInterval(newValue);
    };

    const Label = styled(Typography)({});

    const totalWidth = duration / markInterval * 50;

    return (
      <MainContainer>
        <Dialog open={isErrorDialogOpen} onClose={() => setIsErrorDialogOpen(false)}>
          <DialogTitle>Error</DialogTitle>
          <DialogContent>
            <DialogContentText>{error}</DialogContentText>
          </DialogContent>
          <DialogActions>
            <Button onClick={() => setIsErrorDialogOpen(false)}>Close</Button>
          </DialogActions>
        </Dialog>
        <ControlsContainer>
          <Box>
            <Label variant="body2">
              Mark Interval (s):
            </Label>
            <input
              type="number"
              value={markInterval}
              onChange={handleMarkIntervalChange}
              style={{ width: '100px', marginRight: '20px' }}
            />
          </Box>
          <Button onClick={collectData} variant="contained">
            Save and Send Data
          </Button>
          <Button onClick={handleAddAxis} variant="contained">
            Add New Axis
          </Button>
          <Button onClick={() => setIsDialogOpen(true)} variant="contained">Manage Axes</Button>
        </ControlsContainer>
        <div style={{ display: 'flex', width: '100%' }}>
          <ButtonsContainer>
            {axes.map((axis, index) => (
              <Button
                key={index}
                onClick={() => handleCreateBlock(axis.id)}
                variant="contained"
                sx={{
                  mb: 5, 
                  top:'150px',
                  width: '150px', 
                  height: '42px',
                }} 
              >
                Create
              </Button>
            ))}
          </ButtonsContainer>
          <ScrollableTimelineContainer>
            <div style={{ width: `${totalWidth}px` }}>
              <Slider
                value={seekTime}
                min={0}
                max={duration}
                step={markInterval}
                onChange={handleSliderChange}
                valueLabelDisplay="off"
                marks={marks.map(mark => ({ value: mark.value, label: '' }))}
                sx={{
                  '& .MuiSlider-track': { backgroundColor: 'transparent' },
                  '& .MuiSlider-thumb': {
                    width: '20px',
                    height: '20px',
                    '&:before': { boxShadow: '0 4px 8px rgba(0,0,0,0.4)' },
                  },
                  '& .MuiSlider-rail': { height: '8px', opacity: 0.5 },
                }}
              />
              <AxisManager
                open={isDialogOpen}
                onClose={() => setIsDialogOpen(false)}
                axes={axes}
                annotations={annotations}
                onDeleteAxis={handleDeleteAxis}
                onTypeChange={handleTypeChange}
                onShortcutChange={handleShortcutChange} 
                onNameChange={handleNameChange}
              />
              <Slider
                value={selectedRange}
                min={0}
                max={duration}
                step={markInterval}  // Ensure the step is the same as markInterval
                onChange={handleRangeChange}
                valueLabelDisplay="auto"
                sx={{ marginTop: '20px', marginBottom: '20px' }}
                marks={marks.map(mark => ({ value: mark.value, label: '' }))}
              />
              <TimelineMarks>
                {marks.map((mark, index) => (
                  <TimelineMarkLabel key={index} style={{ left: `${(mark.value / duration) * 100}%` }}>
                    {mark.label}
                  </TimelineMarkLabel>
                ))}
              </TimelineMarks>
              {axes.map((axis) => (
                <Axis
                  key={`${axis.id}-${axis.blocks.length}`}
                  duration={duration}
                  selectedRange={selectedRange}
                  blocks={axis.blocks}
                  axisType={axis.type}
                  axisName={axis.axisName || 'No Axis Name'} 
                  typeName={axis.typeName}
                  annotations={axis.typeName ? annotations[axis.typeName] || [] : []}
                  onSave={(blockIndex, text) => handleSave(axis.id, blockIndex, text)}
                  onDeleteBlock={(blockIndex) => handleDeleteBlock(axis.id, blockIndex)}
                />
              ))}
            </div>
          </ScrollableTimelineContainer>
        </div>
        
      </MainContainer>
    );
  };

  export default Timeline;
