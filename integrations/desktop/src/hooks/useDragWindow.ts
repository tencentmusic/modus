import { useCallback, type MouseEventHandler } from "react";
import { getCurrentWindow } from "@tauri-apps/api/window";

/**
 * Returns a mousedown handler that initiates window dragging via Tauri API.
 */
export function useDragWindow(): MouseEventHandler {
  return useCallback((e) => {
    if (e.buttons === 1 && e.detail === 1) {
      getCurrentWindow().startDragging();
    }
  }, []);
}
