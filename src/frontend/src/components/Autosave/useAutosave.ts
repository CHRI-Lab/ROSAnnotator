// useAutosave.ts
//
// Drives background autosaves from two timers working together:
//
//   * an idle debounce, so a burst of edits results in one write rather than
//     one per drag or keystroke;
//   * a periodic ceiling, so someone editing continuously without pausing is
//     still saved at a predictable worst case.
//
// Both are gated on hasUnsavedEdits, and an unchanged state is never rewritten,
// so an idle session does no disk work.
//
// Note that autosaving does NOT clear hasUnsavedEdits. Only a real "Save and
// Send Data" does that. An autosave is recovery data, not a completed save.

import { useCallback, useEffect, useRef } from "react";
import type { AxisData } from "../../types/annotations";
import {
    buildAutosaveRequestBody,
    postAutosave,
    postAutosaveBeacon,
    AutosaveScope,
} from "./autosaveUtils";

interface UseAutosaveOptions {
    scope?: AutosaveScope;
    enabled: boolean;
    bagFileName: string;
    axes: AxisData[];
    hasUnsavedEdits: boolean;
    bookListFileName?: string;
    annotationFileName?: string;
    annotationName?: string;
    idleDelayMs?: number;
    maxIntervalMs?: number;
    onAutosaved?: (savedAt: string) => void;
    onError?: (error: unknown) => void;
}

export interface AutosaveController {
    // Call after a restore so the hook does not immediately rewrite the file it
    // just read, and after a real save so the next edit is treated as new.
    markSynced: (axes: AxisData[]) => void;
    // Fire an autosave now, ignoring both timers.
    flush: () => Promise<void>;
}

export const useAutosave = (
    options: UseAutosaveOptions
): AutosaveController => {
    const {
        idleDelayMs = 3000,
        maxIntervalMs = 30000,
    } = options;

    // Timers read the latest props through a ref, so the callbacks never need
    // to be rebuilt and no timer is ever cancelled just because a prop changed.
    const latest = useRef(options);
    latest.current = options;

    const idleTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
    const ceilingTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
    const inFlight = useRef<Promise<void> | null>(null);
    const lastSavedSnapshot = useRef<string>("");
    const mounted = useRef(true);

    const clearTimers = useCallback(() => {
        if (idleTimer.current) {
            clearTimeout(idleTimer.current);
            idleTimer.current = null;
        }
        if (ceilingTimer.current) {
            clearTimeout(ceilingTimer.current);
            ceilingTimer.current = null;
        }
    }, []);

    const runAutosave = useCallback(async () => {
        // Serialize writes, then inspect the latest state: edits may have arrived
        // while the previous background request was pending.
        while (inFlight.current) await inFlight.current;
        if (!mounted.current) return;
        const current = latest.current;

        if (!current.enabled || !current.bagFileName) return;
        if (!current.hasUnsavedEdits) return;

        const body = buildAutosaveRequestBody({
            scope: current.scope,
            bagFileName: current.bagFileName,
            bookListFileName: current.bookListFileName,
            annotationFileName: current.annotationFileName,
            annotationName: current.annotationName,
            axes: current.axes,
        });

        const snapshot = JSON.stringify(body.axes);
        if (snapshot === lastSavedSnapshot.current) return;

        const pending = postAutosave(body);
        inFlight.current = pending;
        try {
            await pending;
            lastSavedSnapshot.current = snapshot;
            current.onAutosaved?.(body.saved_at);
        } catch (error) {
            // A failed autosave is not worth interrupting the user for. The
            // next timer tick will try again.
            console.warn("Autosave failed.", error);
            current.onError?.(error);
            throw error;
        } finally {
            inFlight.current = null;
        }
    }, []);

    // Idle debounce: restarted on every edit.
    useEffect(() => {
        if (idleTimer.current) {
            clearTimeout(idleTimer.current);
            idleTimer.current = null;
        }

        if (!options.enabled || !options.hasUnsavedEdits) return;

        idleTimer.current = setTimeout(() => {
            idleTimer.current = null;
            void runAutosave().catch(() => {});
        }, idleDelayMs);
    }, [options.axes, options.hasUnsavedEdits, options.enabled, idleDelayMs, runAutosave]);

    // Ceiling: started once when the state first goes dirty, then repeating.
    useEffect(() => {
        if (!options.enabled || !options.hasUnsavedEdits) {
            if (ceilingTimer.current) {
                clearTimeout(ceilingTimer.current);
                ceilingTimer.current = null;
            }
            return;
        }

        if (ceilingTimer.current) return;

        const tick = () => {
            void runAutosave().catch(() => {}).finally(() => {
                if (mounted.current && latest.current.enabled && latest.current.hasUnsavedEdits) {
                    ceilingTimer.current = setTimeout(tick, maxIntervalMs);
                } else {
                    ceilingTimer.current = null;
                }
            });
        };

        ceilingTimer.current = setTimeout(tick, maxIntervalMs);
    }, [options.enabled, options.hasUnsavedEdits, maxIntervalMs, runAutosave]);

    // Best-effort save when the tab closes. Crash recovery does not depend on
    // this, since a crash never fires it.
    useEffect(() => {
        const handleBeforeUnload = () => {
            const current = latest.current;
            if (!current.enabled || !current.bagFileName) return;
            if (!current.hasUnsavedEdits) return;

            postAutosaveBeacon(
                buildAutosaveRequestBody({
                    scope: current.scope,
                    bagFileName: current.bagFileName,
                    bookListFileName: current.bookListFileName,
                    annotationFileName: current.annotationFileName,
                    annotationName: current.annotationName,
                    axes: current.axes,
                })
            );
        };

        window.addEventListener("beforeunload", handleBeforeUnload);
        return () => window.removeEventListener("beforeunload", handleBeforeUnload);
    }, []);

    useEffect(() => {
        mounted.current = true;
        return () => {
            mounted.current = false;
            clearTimers();
        };
    }, [clearTimers]);

    const markSynced = useCallback((axes: AxisData[]) => {
        lastSavedSnapshot.current = JSON.stringify(
            buildAutosaveRequestBody({
                bagFileName: latest.current.bagFileName,
                axes,
            }).axes
        );
    }, []);

    const flush = useCallback(async () => {
        await runAutosave();
    }, [runAutosave]);

    return { markSynced, flush };
};

export default useAutosave;
