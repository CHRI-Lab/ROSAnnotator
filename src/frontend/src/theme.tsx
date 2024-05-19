import { createTheme } from '@mui/material/styles';

export const darkTheme = createTheme({
  palette: {
    mode: 'dark',
    primary: {
      main: '#90caf9',  // A soft blue, good for primary actions and buttons
    },
    secondary: {
      main: '#f48fb1',  // A softer pink, useful for highlighting secondary elements
    },
    background: {
      default: '#121212',  // Very dark grey for backgrounds
      paper: '#1e1e1e',    // Slightly lighter grey for surfaces like cards, dialogs, etc.
    },
    text: {
      primary: '#e0e0e0',  // Bright enough for readability on dark backgrounds
      secondary: '#b0bec5', // Slightly muted for less critical text elements
    },
    error: {
      main: '#f44336', // Red, used for error states and buttons
    },
    warning: {
      main: '#ffa726', // Orange, used for warnings and cautions
    },
    info: {
      main: '#29b6f6', // Light blue, for informational purposes
    },
    success: {
      main: '#66bb6a', // Green, indicating success states
    },
  },
  typography: {
    fontFamily: [
      'Roboto', 'Helvetica', 'Arial', 'sans-serif'
    ].join(','),
    h1: {
      fontWeight: 300,
    },
    h2: {
      fontWeight: 400,
    },
    h3: {
      fontWeight: 400,
    },
    h4: {
      fontWeight: 400,
    },
    h5: {
      fontWeight: 400,
    },
    h6: {
      fontWeight: 500,
    },
    subtitle1: {
      fontWeight: 400,
    },
    subtitle2: {
      fontWeight: 500,
    },
    body1: {
      fontWeight: 400,
    },
    body2: {
      fontWeight: 400,
    },
    button: {
      textTransform: 'none'  // Avoid uppercase buttons for a more modern look
    },
  },
  components: {
    MuiButton: {
      styleOverrides: {
        root: {
          borderRadius: 4,  // Rounded edges for buttons
        },
      },
    },
  },
});
