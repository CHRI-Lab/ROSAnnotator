import { CSSProperties, useCallback, useEffect } from "react";
import { styled } from "@mui/system";
import { Lrc, LrcLine } from "react-lrc";
import { Box } from "@mui/material";

interface TranscriptProps {
  LRC: string; // LRC string to be displayed
  played: number;
  setPlayed: (time: number) => void; // Function to update the played state
}

// Styles for the LRC component
const lrcStyle: CSSProperties = {
  flex: 1,
  minHeight: 0,
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
const Transcript: React.FC<TranscriptProps> = ({ LRC, played, setPlayed }) => {
  // const [LRC, setLRC] = useState<string>("");

  useEffect(() => {
    // const srtContent = fs.readFileSync(lrcPath, "utf-8");
    // setLRC(srtContent);
  }, []);

  // Function to render each line of the LRC
  const lineRenderer = useCallback(
    ({
      active,
      line: { content, startMillisecond },
    }: {
      active: boolean;
      line: LrcLine;
    }) => (
      <Line active={active} onClick={() => setPlayed(startMillisecond / 1000)}>
        {content.slice(0, -7)}
      </Line>
    ),
    [setPlayed]
  );

  return (
    <Box
      width="100%"
      height="100%"
      display="flex"
      flexDirection="column"
      style={{ overflowY: "auto" }} // Enable scrolling if content overflows
    >
      <Lrc
        lrc={LRC}
        lineRenderer={lineRenderer}
        currentMillisecond={played * 1000} // Convert seconds to milliseconds
        verticalSpace
        style={{ ...lrcStyle, maxHeight: "400px", overflowY: "scroll" }} // Add maxHeight and scroll
        recoverAutoScrollInterval={1000} // Reduce scroll recovery interval
      />
    </Box>
  );
};

export default Transcript;
