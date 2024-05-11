
import React from 'react';
import { Dialog, DialogTitle, DialogContent, DialogActions, Button, List, ListItem, ListItemText, MenuItem, Select } from '@mui/material';


interface AxisData {
  id: number;
  type: string;
  typeName?: string;  
  blocks: any[];
}

interface AxisManagerProps {
  open: boolean;
  onClose: () => void;
  axes: AxisData[];
  annotations: any;
  onDeleteAxis: (axisId: number) => void;
  onTypeChange: (axisId: number, type: string, typeName?: string) => void;
}

const AxisManager: React.FC<AxisManagerProps> = ({ open, onClose, axes, annotations, onDeleteAxis, onTypeChange }) => {
  return (
    <Dialog open={open} onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle>Manage Axes</DialogTitle>
      <DialogContent>
        <List>
          {axes.map((axis, index) => (
            <ListItem key={axis.id} divider>
              <ListItemText 
                primary={`Axis ID: ${axis.id}`} 
                secondary={`Type: ${axis.type} ${axis.typeName ? `- ${axis.typeName}` : ''}`} 
              />
              <Select
                value={axis.type}
                onChange={(event) => onTypeChange(axis.id, event.target.value as string)}
                style={{ marginRight: '10px' }}
              >
                <MenuItem value="type-in">Type-in</MenuItem>
                <MenuItem value="selected">Selected</MenuItem>
              </Select>
              {axis.type === 'selected' && (
                <Select
                  value={axis.typeName || ''} 
                  onChange={(event) => onTypeChange(axis.id, axis.type, event.target.value as string)}
                  style={{ marginRight: '10px', width: '150px' }}
                >
                  {Object.keys(annotations).map((key) => (
                    <MenuItem key={key} value={key}>{key}</MenuItem>
                  ))}
                </Select>
              )}
              <Button variant="outlined" color="secondary" onClick={() => onDeleteAxis(axis.id)}>
                Delete
              </Button>
            </ListItem>
          ))}
        </List>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose} color="primary">Close</Button>
      </DialogActions>
    </Dialog>
  );
};


export default AxisManager;
