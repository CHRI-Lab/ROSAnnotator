import { CSSProperties, useCallback, useEffect, useRef } from "react";
import { styled } from "@mui/system";
import { Lrc, LrcLine } from "react-lrc";
import { Box, Button } from "@mui/material";

interface TranscriptProps {
  LRC: string; // LRC string to be displayed
  played: number;
  isPlaying: boolean;
  setPlayed: (time: number) => void; // Function to update the played state
  onEdit?: () => void;
}

// Styles for the LRC component
const lrcStyle: CSSProperties = {
  flex: 1,
  minHeight: 0,
  height: "100%",
  overflowY: "auto",
};

// Styled component for each line of the transcript
const Line = styled("div")<{ active: boolean }>`
  min-height: 10px;
  padding: 5px 20px;
  font-size: 16px;
  text-align: center;
  color: ${({ active }) => (active ? "dodgerblue" : "lightgrey")};
  cursor: pointer; // Add cursor pointer to indicate clickability
`;

// The main Transcript component
const Transcript: React.FC<TranscriptProps> = ({
  LRC,
  played,
  isPlaying,
  setPlayed,
  onEdit,
}) => {
  const containerRef = useRef<HTMLDivElement | null>(null);

  const keepActiveLineVisible = useCallback(() => {
    window.requestAnimationFrame(() => {
      const container = containerRef.current;
      const activeLine = container?.querySelector<HTMLElement>(
        '[data-transcript-active="true"]'
      );
      if (!container || !activeLine) return;

      const containerBounds = container.getBoundingClientRect();
      const lineBounds = activeLine.getBoundingClientRect();
      if (
        lineBounds.top < containerBounds.top ||
        lineBounds.bottom > containerBounds.bottom
      ) {
        activeLine.scrollIntoView({ block: "nearest", inline: "nearest" });
      }
    });
  }, []);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const resizeObserver = new ResizeObserver(() => {
      if (isPlaying) keepActiveLineVisible();
    });
    resizeObserver.observe(container);
    return () => resizeObserver.disconnect();
  }, [isPlaying, keepActiveLineVisible]);

  useEffect(() => {
    if (isPlaying) keepActiveLineVisible();
  }, [isPlaying, keepActiveLineVisible]);

  // Function to render each line of the LRC
  const lineRenderer = useCallback(
    ({
      active,
      line: { content, startMillisecond },
    }: {
      active: boolean;
      line: LrcLine;
    }) => (
      <Line
        active={active}
        data-transcript-active={active ? "true" : undefined}
        onClick={() => setPlayed(startMillisecond / 1000)}
      >
        {content.replace(/\s*\[\d+:\d{2}\]\s*$/, "")}
      </Line>
    ),
    [setPlayed]
  );

  return (
    <Box
      ref={containerRef}
      width="100%"
      height="100%"
      display="flex"
      flexDirection="column"
      overflow="hidden"
    >
      {onEdit && <Box display="flex" justifyContent="flex-end" px={1} flexShrink={0}>
        <Button onClick={onEdit}>Edit transcript</Button>
      </Box>}
      <Lrc
        lrc={LRC}
        lineRenderer={lineRenderer}
        currentMillisecond={played * 1000} // Convert seconds to milliseconds
        verticalSpace
        style={lrcStyle}
        recoverAutoScrollInterval={isPlaying ? 1000 : 1}
        onLineUpdate={() => {
          if (isPlaying) keepActiveLineVisible();
        }}
      />
    </Box>
  );
};

export default Transcript;
