import React from 'react';
import ReactDOM from 'react-dom';
import App from './App.tsx';

import { ThemeProvider } from '@mui/material/styles';
import { darkTheme } from "./theme";
import { CssBaseline } from '@mui/material';

ReactDOM.render(
  <React.StrictMode>
    <ThemeProvider theme={darkTheme}>
      <CssBaseline />
      <App />
    </ThemeProvider>
  </React.StrictMode>,
  document.getElementById('root')
);
