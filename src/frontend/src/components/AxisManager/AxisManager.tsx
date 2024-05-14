import React from 'react';
import { Dialog, DialogTitle, DialogContent, DialogActions, Button, List, ListItem, ListItemText, MenuItem, Select, TextField, Tooltip } from '@mui/material';

interface BlockProps {
  start: number;
  end: number;
  text?: string;
}

interface AxisData {
  id: number;
  type: string;
  typeName?: string;
  shortcutKey?: string;  
  blocks: BlockProps[];
}

interface AxisManagerProps {
  open: boolean;
  onClose: () => void;
  axes: AxisData[];
  annotations: any;
  onDeleteAxis: (axisId: number) => void;
  onTypeChange: (axisId: number, type: string, typeName?: string) => void;
  onShortcutChange: (axisId: number, shortcutKey: string) => void;
  onRenameAxis: (axisId: number, typeName: string) => void;
}

const AxisManager: React.FC<AxisManagerProps> = ({
  open,
  onClose,
  axes,
  annotations,
  onDeleteAxis,
  onTypeChange,
  onShortcutChange,
  onRenameAxis
}) => {
  return (
    <Dialog open={open} onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle>Manage Axes</DialogTitle>
      <DialogContent>
        <List>
          {axes.map((axis, ) => (
            <ListItem key={axis.id} divider>
              <ListItemText
                primary={`Axis ID: ${axis.id}`}
                secondary={`Type: ${axis.type}${axis.typeName ? ` - ${axis.typeName}` : ''}`}
              />
              <TextField
                label="Rename Axis"
                value={axis.typeName || ''}
                onChange={(event) => onRenameAxis(axis.id, event.target.value)}
                style={{ marginRight: '10px' }}
              />
              <Select
                value={axis.type}
                onChange={(event) => onTypeChange(axis.id, event.target.value as string, axis.typeName)}
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
              <Tooltip title="Set a shortcut key to quickly create an annotation block on this axis">
                <TextField
                  label="Shortcut Key"
                  value={axis.shortcutKey || ''}
                  onChange={(event) => onShortcutChange(axis.id, event.target.value)}
                  style={{ width: '200px', marginLeft: '0px',marginRight:'10px' }}
                  inputProps={{ maxLength: 1 }}
                />
              </Tooltip>
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
