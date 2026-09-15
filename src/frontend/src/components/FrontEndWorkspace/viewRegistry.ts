import { dataViewDefinitions } from "./dataViews";
import type { DataViewDefinition } from "./viewTypes";

export const availableViews: DataViewDefinition[] = dataViewDefinitions;

export type { DataViewDefinition, ViewPanelContext } from "./viewTypes";
