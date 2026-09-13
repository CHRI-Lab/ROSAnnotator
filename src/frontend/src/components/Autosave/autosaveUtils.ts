// autosaveUtils.ts
//
// Sits alongside saveUtils.ts. saveUtils.ts handles the deliberate CSV export
// ("Save and Send Data"); this file handles the background crash-recovery copy.
//
// The two collectors are deliberately separate. collectAnnotationData() shapes
// data for the CSV writer, which drops empty axes and shortcut keys. Recovery
// needs the state back exactly as it was, so collectAutosaveState() keeps
// everything.

const API_BASE = "http://localhost:8000";

export const AUTOSAVE_SCHEMA_VERSION = 1; //ensures if schema updates, alt versions are NOT accepted

export interface AutosaveScope {
    manifest_id: string;
    chunk_index: number;
}

const scopeQuery = (scope?: AutosaveScope) => scope
    ? `&manifest_id=${encodeURIComponent(scope.manifest_id)}&chunk_index=${scope.chunk_index}`
    : "";

export interface AutosaveBlock {
    start: number;
    end: number;
    text: string;
}

export interface AutosaveAxis {
    id: number;
    type: string;
    axisName: string;
    typeName: string;
    shortcutKey: string;
    blocks: AutosaveBlock[];
}

export interface AutosaveRequestBody {
    manifest_id?: string;
    chunk_index?: number;
    bag_filename: string;
    booklist_filename: string;
    annotation_filename: string;
    annotation_name: string;
    saved_at: string;
    axes: AutosaveAxis[];
}

export interface AutosaveMeta {
    exists: boolean;
    bag_filename?: string;
    booklist_filename?: string;
    annotation_filename?: string;
    annotation_name?: string;
    saved_at?: string;
    axis_count?: number;
    block_count?: number;
    recovered_from_backup?: boolean;
}

export interface AutosavePayload extends AutosaveMeta {
    manifest_id?: string;
    chunk_index?: number;
    schema_version: number;
    axes: AutosaveAxis[];
}

// Captures the full editing state, including axes with no blocks and any
// shortcut keys the user has assigned. Nothing here is allowed to drop data.
export const collectAutosaveState = (axes: any[]): AutosaveAxis[] =>
    (axes || []).map((axis) => ({
        id: axis.id,
        type: axis.type ?? "type-in",
        axisName: axis.axisName ?? "",
        typeName: axis.typeName ?? "",
        shortcutKey: axis.shortcutKey ?? "",
        blocks: (axis.blocks ?? []).map((block: any) => ({
            start: block.start,
            end: block.end,
            text: block.text ?? "",
        })),
    }));

// The timestamp is stamped by the browser, not the server. The backend runs in
// a container on UTC, so a server-side time would show Melbourne users a
// recovery prompt that is hours out.
export const buildAutosaveRequestBody = (options: {
    scope?: AutosaveScope;
    bagFileName: string;
    bookListFileName?: string;
    annotationFileName?: string;
    annotationName?: string;
    axes: any[];
}): AutosaveRequestBody => ({
    ...options.scope,
    bag_filename: options.bagFileName,
    booklist_filename: options.bookListFileName ?? "",
    annotation_filename: options.annotationFileName ?? "",
    annotation_name: options.annotationName ?? "",
    saved_at: new Date().toISOString(),
    axes: collectAutosaveState(options.axes),
});

export const postAutosave = async (body: AutosaveRequestBody): Promise<void> => {
    const response = await fetch(`${API_BASE}/api/autosave/save/`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
    });

    if (!response.ok) {
        throw new Error(`Autosave failed: ${response.status}`);
    }
};

// Used on tab close only. A normal fetch is not guaranteed to complete during
// unload; sendBeacon is queued by the browser and survives the page going away.
export const postAutosaveBeacon = (body: AutosaveRequestBody): boolean => {
    if (typeof navigator === "undefined" || !navigator.sendBeacon) {
        return false;
    }
    const blob = new Blob([JSON.stringify(body)], { type: "application/json" });
    return navigator.sendBeacon(`${API_BASE}/api/autosave/save/`, blob);
};

// Metadata only, for the import-page prompt. Cheap even for long recordings.
export const fetchAutosaveMeta = async (
    bagFileName: string, scope?: AutosaveScope
): Promise<AutosaveMeta> => {
    const url = `${API_BASE}/api/autosave/check/?bag_filename=${encodeURIComponent(
        bagFileName
    )}`;
    const response = await fetch(url + scopeQuery(scope));

    if (!response.ok) {
        throw new Error(`Autosave check failed: ${response.status}`);
    }
    return response.json();
};

// The full payload, fetched only once the user chooses to restore.
export const fetchAutosave = async (
    bagFileName: string, scope?: AutosaveScope
): Promise<AutosavePayload> => {
    const url = `${API_BASE}/api/autosave/load/?bag_filename=${encodeURIComponent(
        bagFileName
    )}`;
    const response = await fetch(url + scopeQuery(scope));

    if (!response.ok) {
        throw new Error(`Autosave load failed: ${response.status}`);
    }
    return response.json();
};

export const deleteAutosave = async (bagFileName: string, scope?: AutosaveScope): Promise<boolean> => {
    const url = `${API_BASE}/api/autosave/delete/?bag_filename=${encodeURIComponent(
        bagFileName
    )}`;
    const response = await fetch(url + scopeQuery(scope), { method: "DELETE" });

    if (!response.ok) {
        throw new Error(`Autosave delete failed: ${response.status}`);
    }
    const data = await response.json();
    return Boolean(data.deleted);
};

// "14:32 today" for same-day recoveries, full date and time otherwise.
export const formatAutosaveTimestamp = (isoTimestamp?: string): string => {
    if (!isoTimestamp) {
        return "an earlier session";
    }

    const saved = new Date(isoTimestamp);
    if (Number.isNaN(saved.getTime())) {
        return "an earlier session";
    }

    const now = new Date();
    const sameDay =
        saved.getFullYear() === now.getFullYear() &&
        saved.getMonth() === now.getMonth() &&
        saved.getDate() === now.getDate();

    const time = saved.toLocaleTimeString([], {
        hour: "2-digit",
        minute: "2-digit",
    });

    return sameDay ? `${time} today` : saved.toLocaleString();
};

// Converts a stored autosave back into the axis shape Timeline holds in state.
// The shapes already match, so this is mostly a defensive copy with defaults.
export const hydrateAutosaveAxes = (axes: AutosaveAxis[]): any[] =>
    (axes || []).map((axis) => ({
        id: axis.id,
        type: axis.type ?? "type-in",
        axisName: axis.axisName ?? "",
        typeName: axis.typeName ?? "",
        shortcutKey: axis.shortcutKey ?? "",
        blocks: axis.blocks ?? [],
    }));

// Timeline's globalAxisId counter must resume above every restored id, or the
// next "Add New Axis" produces a duplicate id and every handler that matches
// axes by id starts hitting the wrong axis.
export const highestAxisId = (axes: any[]): number =>
    (axes || []).reduce(
        (max, axis) =>
            Number.isFinite(axis?.id) && axis.id > max ? axis.id : max,
        0
    );
