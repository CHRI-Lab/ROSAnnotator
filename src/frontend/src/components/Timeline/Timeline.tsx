import React, { useState, useEffect, useContext } from "react";
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

let globalAxisId = 0;

interface TimelineProps {
  rosBagFileName: string;
  bookListFileName: string;
  duration: number;
  played: number;
  onSeek: (time: number) => void;
  booklist: any;
  annotationData: any;
  speakerData?: Array<any>;
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
      const speakerAxes = speakerData.map((segment) => ({
        id: globalAxisId++,
        type: "speakers",
        axisName: segment.speaker_label,
        blocks: [
          {
            start: segment.start_time,
            end: segment.end_time,
            text: segment.text,
          },
        ],
        shortcutKey: segment.speaker_label.charAt(0).toUpperCase(),
      }));
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
      const response = await fetch("http://0.0.0.0:8000/api/save_annotation/", {
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

  const handleRangeChange = (_event: Event, newValue: number | number[]) => {
    setSelectedRange(newValue as number[]);
  };

  const handleAddAxis = () => {
    setAxes((prev) => [
      ...prev,
      { id: globalAxisId++, type: "type-in", blocks: [] },
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
                key={`${axis.id}-${axis.blocks.length}`}
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
  );
};

export default Timeline;
