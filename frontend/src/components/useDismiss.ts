import { type RefObject, useEffect } from "react";

// Closes a panel on a click outside its container and on Escape, from document listeners
// rather than a keydown handler on a non-interactive div (sonar S6847). onDismiss is told
// whether to hand focus back: Escape came from the keyboard and wants the trigger again,
// a click already put focus where it landed.
export function useDismiss(
  open: boolean,
  containerRef: RefObject<HTMLElement | null>,
  onDismiss: (restoreFocus: boolean) => void,
) {
  useEffect(() => {
    if (!open) {
      return undefined;
    }
    function handlePointerDown(event: PointerEvent) {
      if (!containerRef.current?.contains(event.target as Node)) {
        onDismiss(false);
      }
    }
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        onDismiss(true);
      }
    }
    document.addEventListener("pointerdown", handlePointerDown);
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("pointerdown", handlePointerDown);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [open, containerRef, onDismiss]);
}
