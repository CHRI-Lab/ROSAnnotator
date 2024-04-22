import React from 'react';
import Snackbar from '@mui/material/Snackbar';
import IconButton from '@mui/material/IconButton';

interface CustomSnackbarProps {
  open: boolean;
  message: string;
  handleClose: () => void;
}

const CustomSnackbar: React.FC<CustomSnackbarProps> = ({ open, message, handleClose }) => {
  return (
    <Snackbar
      open={open}
      autoHideDuration={3000}
      onClose={handleClose}
      message={message}
      action={
        <IconButton
          size="small"
          aria-label="close"
          color="inherit"
          onClick={handleClose}
        >
        </IconButton>
      }
    />
  );
};

export default CustomSnackbar;
