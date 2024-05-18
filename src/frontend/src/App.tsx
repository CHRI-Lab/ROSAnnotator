import React, { useState, useCallback } from 'react';
import ReactPlayer from 'react-player';
import Box from '@mui/material/Box';
import TextField from '@mui/material/TextField';
import { createTheme, ThemeProvider } from '@mui/material/styles';

import Timeline from './components/Timeline';
import Transcript from './components/Transcript';

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

  const playerRef = useCallback((playerInstance: ReactPlayer) => {
    setPlayer(playerInstance);
  }, []);

  return (
    <ThemeProvider theme={theme}>
      <Box display="flex" justifyContent="center" alignItems="center" flexDirection="column">
        <Box display="flex" justifyContent="center" alignItems="center" flexDirection="row">
          <Box width={600} height={452}>
            <Transcript played={played}/>
          </Box>
          <Box width="100%" height={452} maxWidth={602}> 
            <ReactPlayer
              ref={playerRef}
              width="100%"
              height="auto" 
              url="sample.mp4"
              onDuration={handleDuration}
              onProgress={handleProgress}
              controls
              playing
            />
          </Box>
        </Box>
        <Box width="100%" maxWidth={1200}> 
          <Timeline
            duration={duration}
            played={played}
            markInterval={markInterval}
            onSeek={handleSeek}
          />
        </Box>
        <Box width="100%" maxWidth={200}>
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