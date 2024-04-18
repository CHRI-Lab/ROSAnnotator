import React, { useState, useCallback, useRef } from 'react';
import ReactPlayer from 'react-player';
import Timeline from './Timeline';
import Box from '@mui/material/Box';
import TextField from '@mui/material/TextField';
import { createTheme, ThemeProvider } from '@mui/material/styles';

const theme = createTheme();

const App: React.FC = () => {
  const [player, setPlayer] = useState<ReactPlayer | null>(null);
  const [duration, setDuration] = useState(0);
  const [played, setPlayed] = useState(0);
  const [markInterval, setMarkInterval] = useState(5);

  const handleDuration = (duration: number) => {
    setDuration(duration);
  };

  const handleProgress = (progress: { playedSeconds: number }) => {
    if (!isNaN(progress.playedSeconds)) {
      setPlayed(progress.playedSeconds);
    }
  };

  const handleSeek = useCallback((time: number) => {
    setPlayed(time);
    if (player) {
      player.seekTo(time);
    }
  }, [player]);

  const handleChangeMarkInterval = (event: React.ChangeEvent<HTMLInputElement>) => {
    const interval = Math.max(1, Number(event.target.value));
    setMarkInterval(interval);
  };

  const ref = useCallback((playerInstance: ReactPlayer) => {
    setPlayer(playerInstance);
  }, []);

  return (
    <ThemeProvider theme={theme}>
      <Box display="flex" justifyContent="center" alignItems="center" height="100vh" flexDirection="column">
        <Box width="100%" maxWidth={300} marginBottom={2}> 
          <ReactPlayer
            ref={ref}
            width="100%"
            height="auto" 
            url="test2.mp4"
            onDuration={handleDuration}
            onProgress={handleProgress}
            controls
            playing
          />
        </Box>
        <Box width="100%" maxWidth={720}> 
          <Timeline
            duration={duration}
            played={played}
            markInterval={markInterval}
            onSeek={handleSeek}
          />
        </Box>
        <Box width="100%" maxWidth={720}>
          <TextField
            label="Mark interval (seconds)"
            type="number"
            value={markInterval}
            onChange={handleChangeMarkInterval}
            InputProps={{ inputProps: { min: 1 } }}
            variant="outlined"
            fullWidth
          />
        </Box>
      </Box>
    </ThemeProvider>
  );
};

export default App;
