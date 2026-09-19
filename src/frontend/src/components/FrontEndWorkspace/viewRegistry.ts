import { dataViewDefinitions } from "./dataViews";
import type { BackendDataView, DataViewDefinition } from "./viewTypes";

export const availableViews: DataViewDefinition[] = dataViewDefinitions;

export function viewsWithAvailability(views?: Record<string, BackendDataView>) {
  return availableViews.map(view => ({
    ...view,
    available: views ? views[view.id]?.status === 'ready' && views[view.id]?.available === true && views[view.id]?.processed_data != null : true,
    reason: views?.[view.id]?.reason ?? (views && !views[view.id] ? 'No data returned for this view.' : null),
    status: views?.[view.id]?.status,
  }));
}

export type { DataViewDefinition, ViewPanelContext } from "./viewTypes";
