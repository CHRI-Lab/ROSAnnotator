import type { ReactElement } from "react";
import type { DataViewDefinition, ViewPanelContext } from "./viewTypes";

/** Shared view contract. Times and callbacks use seconds within current media. */
export abstract class BaseDataView {
  abstract readonly id: string;
  abstract readonly label: string;

  /** Return a React element for the supplied playback state and callbacks. */
  abstract render(context: ViewPanelContext): ReactElement;

  // Stable identity prevents React remounting a player on each progress update.
  private readonly component = (context: ViewPanelContext): ReactElement =>
    this.render(context);

  /** Keep Cassie's existing registry/selector/panel interface intact. */
  toDefinition(): DataViewDefinition {
    return { id: this.id, label: this.label, component: this.component };
  }
}
