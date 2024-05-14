// MainContent.tsx
import React, { useState, useCallback } from 'react';
import ReactPlayer from 'react-player';
import Box from '@mui/material/Box';
import { createTheme, ThemeProvider } from '@mui/material/styles';
import Button from '@mui/material/Button';
import { Dialog, DialogActions, DialogContent, Grid } from '@mui/material';

import Timeline from '../../components/Timeline';
import Transcript from '../../components/Transcript';
import Booklist from '../../components/Booklist/Booklist';
import EditBooklistForm from '../../components/EditBooklistForm/EditBooklistForm';

import annotationsData from '../../../public/predefined_booklist.json';

const theme = createTheme();

const Annotator: React.FC = () => {
  const [player, setPlayer] = useState<ReactPlayer | null>(null);
  const [duration, setDuration] = useState(0);
  const [played, setPlayed] = useState(0);
  const [open, setOpen] = useState(false);
  const [editMode, setEditMode] = useState(false);

  const handleSaveBooklist = (jsonData: any) => {
    console.log(jsonData)
    fetch('/api/saveBooklist', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify(jsonData)
    })
    .then(response => response.json())
    .then(data => {
      console.log('Success:', data);
      alert('Data saved successfully!');
    })
    .catch((error) => {
      console.error('Error:', error);
      alert('Failed to save data.');
    });
  };

  const handleDuration = (duration: number) => {
    setDuration(duration);
  };

    const handleClickOpen = () => {
      setOpen(true);
      setEditMode(false);
  };

  const handleClose = () => {
      setOpen(false);
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

  const playerRef = useCallback((playerInstance: ReactPlayer) => {
    setPlayer(playerInstance);
  }, []);

  const handleEdit = () => {
    setEditMode(true);
};

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
        <div>
          <Box sx={{ position: 'absolute', top: 0, left: 0, padding: 2 }}>
              <Button variant="outlined" onClick={handleClickOpen}>
                  Booklist
              </Button>
              <Dialog open={open} onClose={handleClose} maxWidth="md" fullWidth>
                  <DialogContent>
                    <Grid container spacing={2}>
                        {editMode ? <EditBooklistForm onSave={handleSaveBooklist} /> : <Booklist />}
                    </Grid>
                  </DialogContent>
              <DialogActions>
              {!editMode && <Button onClick={handleEdit}>Edit</Button>}
                <Button onClick={handleClose}>Close</Button>
                
                    
                  </DialogActions>
              </Dialog>
          </Box>
        </div>
        
        <Box width="100%" maxWidth={1200}>
          <Timeline
            duration={duration}
            played={played}
            annotations={annotationsData} 
            onSeek={handleSeek}
          />
        </Box>
      </Box>
    </ThemeProvider>
  );
};

export default Annotator;
