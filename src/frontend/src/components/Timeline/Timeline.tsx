import React, { useState, useEffect, useContext } from "react";
import { Droppable, Draggable, DragDropContext, DropResult } from 'react-beautiful-dnd';
import {
  Box,
  Button,
  Slider,
  Paper,
  Dialog,
  DialogTitle,
  DialogActions,
  DialogContent,
  DialogContentText,
  Typography,
} from "@mui/material";
import { styled } from "@mui/system";
import Axis from "../Axis";
import AxisManager from "../AxisManager";
import AxesContext from "../AxesProvider";

let globalAxisId = 1;


interface TimelineProps {
  rosBagFileName: string;
  bookListFileName: string;
  duration: number;
  played: number;
  onSeek: (time: number) => void;
  booklist: any;
  annotationData: any;
  speakerData?: Array<any>;
  onAxesUpdate: (axes: any) => void;//Send information to parent
  instruction: any;
}

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
  rosBagFileName,
  bookListFileName,
  duration,
  played,
  onSeek,
  booklist,
  annotationData,
  speakerData,
  onAxesUpdate,
  instruction,
}) => {
  const [seekTime, setSeekTime] = useState(played);
  const [markInterval, setMarkInterval] = useState(1);
  const [selectedRange, setSelectedRange] = useState<number[]>([
    0,
    0.1 * duration,
  ]);
  const [isDialogOpen, setIsDialogOpen] = useState(false);
  const [error, setError] = useState("");
  const [isErrorDialogOpen, setIsErrorDialogOpen] = useState(false);

  const { axes, setAxes } = useContext(AxesContext)!;

  useEffect(() => {
    if (instruction) {
      handleExecuteInstruction(instruction); // 如果接收到新的指令，就执行
    }
  }, [instruction]);

  useEffect(() => {
    if (onAxesUpdate) {
      onAxesUpdate(axes);
    }
  }, [axes, onAxesUpdate]);
  
  const handleExecuteInstruction = (instruction) => {
    instruction.steps.forEach((step) => {
      const { action, parameters } = step;
  
      switch (action) {
        case "addAxi":
          const { axisId, axisName, axistype } = parameters;
          handleAddAxis_gpt(axisId, axisName, axistype); // 调用已有的添加 Axis 方法
          break;
  
        case "addBlock":
          const { axisId: blockAxisId, start, end, text } = parameters;
          handleCreateBlockFromInstruction(blockAxisId, start, end, text); // 根据指令添加 Block
          break;
        
        case "deleteBlock":
          const {axisId: deleteAxisId, blockIndex } = parameters;
          handleDeleteBlock(deleteAxisId, blockIndex);
          break

        default:
          console.error(`Unknown action: ${action}`);
      }
    });
  };
  
  const handleCreateBlockFromInstruction = (axisId, start, end, text) => {
    const newBlock = { start, end, text };
  
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


  useEffect(() => {

    if (annotationData) {
      const newAxes = annotationData.map((axisData: any) => ({
        id: globalAxisId++,
        type: axisData.axisType,
        axisName: axisData.axisName,
        typeName: axisData.axisBooklistName,
        blocks: axisData.annotationBlocks,
      }));
      setAxes(newAxes);
    }
  
    if (speakerData) {
      // 创建一个用于存放按 speaker_label 分组的数据的 Map
      const speakerAxesMap = new Map<string, any>();
  
      speakerData.forEach((segment) => {
        const speakerLabel = segment.speaker_label;
  
        // 如果 map 中已经有该 speaker_label 的数据，更新 blocks
        if (speakerAxesMap.has(speakerLabel)) {
          const existingAxis = speakerAxesMap.get(speakerLabel);
          existingAxis.blocks.push({
            start: segment.start_time,
            end: segment.end_time,
            text: segment.text,
          });
        } else {
          // 如果 map 中没有该 speaker_label，创建新的 axis 并添加到 map 中
          speakerAxesMap.set(speakerLabel, {
            id: globalAxisId++,
            type: "speakers",
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
  
      // 将 speakerAxesMap 转换为数组并合并到现有 axes 中
      const speakerAxes = Array.from(speakerAxesMap.values());
      setAxes((prevAxes) => [...prevAxes, ...speakerAxes]);
    }
  }, [annotationData, speakerData]);
  useEffect(() => {
    if (annotationData) {
      //TODO check this code
      const newAxes = annotationData.map((axisData: any) => ({
        id: globalAxisId++,
        type: axisData.axisType,
        axisName: axisData.axisName,
        typeName: axisData.axisBooklistName,
        blocks: axisData.annotationBlocks,
      }));
      setAxes(newAxes);
    }
  }, []);

  useEffect(() => {
    const handleKeyPress = (event: KeyboardEvent) => {
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
  }, [axes, selectedRange]);

  useEffect(() => {
    setSeekTime(played);
  }, [played]);

  // Save data through API
  const handleSaveData = async () => {
    const data = collectData();
    console.log(JSON.stringify(data));
    try {
      const response = await fetch("http://localhost:8000/api/save_annotation/", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          annotation_name: `${rosBagFileName}+${
            bookListFileName ? bookListFileName : "noBookList"
          }`,
          annotation_data: data,
        }),
      });

      if (!response.ok) {
        switch (response.status) {
          case 500:
            throw new Error("Internal server error");
          case 400:
            throw new Error("Invalid JSON format");
          case 405:
            throw new Error("Method not allowed");
        }
      } else {
        alert("Data saved successfully.");
      }
    } catch (error) {
      setError("Failed to save data. Please try again.\n" + error);
      setIsErrorDialogOpen(true);
    }
  };

  const collectData = () => {
    const data = axes.map((axis) => ({
      id: axis.id,
      axisType: axis.type,
      axisName: axis.axisName ? axis.axisName : "",
      axisBooklistName: axis.typeName ? axis.typeName : "",
      annotationBlocks: axis.blocks
        ? axis.blocks.map((block) => ({
            start: block.start,
            end: block.end,
            text: block.text,
          }))
        : [],
    }));
    console.log(data);
    return data;
  };

  const handleSliderChange = (_event: Event, newValue: number | number[]) => {
    setSeekTime(newValue as number);
    onSeek(newValue as number);
  };

  const handleDragEnd = (result: DropResult) => {
    const { source, destination } = result;
  
    // 如果没有目标位置，直接返回
    if (!destination) return;
  
    // 查找源轴和目标轴
    const sourceAxis = axes.find((axis) => String(axis.id) === source.droppableId);
    const destinationAxis = axes.find((axis) => String(axis.id) === destination.droppableId);
  
    // 确保源轴和目标轴存在
    if (sourceAxis && destinationAxis) {
      if (sourceAxis == destinationAxis) return;
      const sourceBlocks = [...sourceAxis.blocks];
      const destinationBlocks = [...destinationAxis.blocks];
  
      // 从源轴中移除拖动的 block
      const [movedBlock] = sourceBlocks.splice(source.index, 1);
  
      // 确保 block 被插入到目标轴的正确位置
      destinationBlocks.splice(destination.index, 0, movedBlock);
  
      // 使用回调函数来确保状态更新一致性
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
  const handleAddAxis_gpt = (axisId: number, axisName: string, type: string) => {
    setAxes((prev) => [
      ...prev,
      { 
        id: axisId,
        type: type ,
        axisName: axisName ,
        blocks: []
      },
    ]);
    globalAxisId=globalAxisId++
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
    setAxes(
      axes.map((axis) => {
        if (axis.id === axisId) {
          const newBlocks = axis.blocks.filter(
            (_, index) => index !== blockIndex
          );
          return { ...axis, blocks: newBlocks };
        }
        return axis;
      })
    );
  };

  const handleDeleteAxis = (axisId: number) => {
    setAxes((axes) => axes.filter((axis) => axis.id !== axisId));
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

  const handleSave = (axisId: number, blockIndex: number, newText: string) => {
    setAxes(
      axes.map((axis) => {
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
      })
    );
  };

  const marks = Array.from(
    { length: Math.ceil(duration / markInterval) },
    (_, index) => {
      const value = Math.round(markInterval * index * 10) / 10;
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

  const handleMarkIntervalChange = (
    event: React.ChangeEvent<HTMLInputElement>
  ) => {
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

  const totalWidth = (duration / markInterval) * 50;

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
      <ControlsContainer>
        <Box>
          <Label variant="body2">Mark Interval (s):</Label>
          <input
            type="number"
            value={markInterval}
            onChange={handleMarkIntervalChange}
            style={{ width: "100px", marginRight: "20px" }}
          />
        </Box>
        <Button onClick={handleSaveData} variant="contained">
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
                typeName={axis.typeName}
                booklist={axis.typeName ? booklist[axis.typeName] || [] : []}
                onSave={(blockIndex, text) =>
                  handleSave(axis.id, blockIndex, text)
                }
                onDeleteBlock={(blockIndex) =>
                  handleDeleteBlock(axis.id, blockIndex)
                }
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
