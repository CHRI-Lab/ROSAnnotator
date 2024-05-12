import React from 'react';
import { List, ListItem, ListItemText, Paper, Button } from '@mui/material';

function LoadableList() {
  return (
    <div style={{ display: 'flex', justifyContent: 'space-around', padding: '20px' }}>
      <Paper style={{ width: '30%' }}>
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
        <List component="nav" aria-label="Predefined Booklist">
          <ListItem button>
            <ListItemText primary="Book 1" />
          </ListItem>
          <ListItem button>
            <ListItemText primary="Book 2" />
          </ListItem>
        </List>
        <Button variant="contained" color="primary" style={{ width: '100%' }}>
          Load
        </Button>
      </Paper>
      <Paper style={{ width: '30%' }}>
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
  );
}

export default LoadableList;
