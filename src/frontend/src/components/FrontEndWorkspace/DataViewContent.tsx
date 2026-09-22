import { Component, ReactNode } from 'react';
import { Alert, Box, CircularProgress } from '@mui/material';
import type { DataViewDefinition, ViewPanelContext } from './viewTypes';

class ViewErrorBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() { return { failed: true }; }
  render() {
    return this.state.failed ? <Alert severity="warning">This view could not be displayed.</Alert> : this.props.children;
  }
}

export function DataViewContent({ view, context }: { view: DataViewDefinition; context: ViewPanelContext }) {
  const state = context.views?.[view.id];
  if (state?.status === 'loading') return <CircularProgress aria-label={`Loading ${view.label}`} />;
  if (context.views && (!state?.available || state.status !== 'ready' || state.processed_data == null)) {
    return <Alert severity="info">{state?.reason || `${view.label} has no usable data.`}</Alert>;
  }
  const Content = view.component;
  if (view.id === 'video') return <ViewErrorBoundary key={view.id}>
    <Box sx={{ height: '100%', minHeight: 0, display: 'flex', flexDirection: 'column' }}>
      <Box sx={{ maxHeight: '35%', overflow: 'auto', flexShrink: 0 }}>
        {state?.warnings.map(warning => <Alert severity="warning" key={warning}>{warning}</Alert>)}
      </Box>
      <Box sx={{ flex: 1, minHeight: 0, overflow: 'hidden' }}><Content {...context} /></Box>
    </Box>
  </ViewErrorBoundary>;
  return <ViewErrorBoundary key={view.id}>
    {state?.warnings.map(warning => <Alert severity="warning" key={warning}>{warning}</Alert>)}
    <Content {...context} />
  </ViewErrorBoundary>;
}
