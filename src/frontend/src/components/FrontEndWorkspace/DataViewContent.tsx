import { Component, ReactNode } from 'react';
import { Alert, CircularProgress } from '@mui/material';
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
  return <ViewErrorBoundary key={view.id}>
    {state?.warnings.map(warning => <Alert severity="warning" key={warning}>{warning}</Alert>)}
    <Content {...context} />
  </ViewErrorBoundary>;
}
