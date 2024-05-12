import React from 'react';
import { List, ListItem, ListItemText, Paper, Typography, Button } from '@mui/material';

function LoadableList() {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', justifyContent: 'center', height: '100vh', padding: '20px', marginTop: '200px' }}>
    <div style={{ display: 'flex', justifyContent: 'space-around' }}>
        <Paper style={{ width: '30%' }}>
          <Typography variant="h6" component="h2" style={{ fontWeight: 'bold', textAlign: 'center' }}>
            ROSBAG DATA FILE
          </Typography>
          <List component="nav" aria-label="ROSbag data file">
            <ListItem button>
              <ListItemText primary="Item 1" />
            </ListItem>
            <ListItem button>
              <ListItemText primary="Item 2" />
            </ListItem>
          </List>
        </Paper>
        
        <Paper style={{ width: '30%' }}>
          <Typography variant="h6" component="h2" style={{ fontWeight: 'bold', textAlign: 'center' }}>
            Predefined Booklist
          </Typography>
          <List component="nav" aria-label="Predefined Booklist">
            <ListItem button>
              <ListItemText primary="Book 1" />
            </ListItem>
            <ListItem button>
              <ListItemText primary="Book 2" />
            </ListItem>
          </List>
        </Paper>
        
        <Paper style={{ width: '30%' }}>
          <Typography variant="h6" component="h2" style={{ fontWeight: 'bold', textAlign: 'center' }}>
            Annotation File
          </Typography>
          <List component="nav" aria-label="Annotation File">
            <ListItem button>
              <ListItemText primary="File 1" />
            </ListItem>
            <ListItem button>
              <ListItemText primary="File 2" />
            </ListItem>
          </List>
        </Paper>
      </div>

      <div style={{ display: 'flex', justifyContent: 'center', marginTop: '20px' }}>
        <Button variant="contained" color="primary">Load Me</Button>
      </div>
    </div>
  );
}

export default LoadableList;
