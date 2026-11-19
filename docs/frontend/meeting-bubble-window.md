# Meeting bubble window placement

The bubble is the Tauri window `mini` (`desktop/src-tauri/src/lib.rs`, `create_bubble`). Its size follows
the content through `resizeMiniWindow` in `desktop/src/shared/lib/miniWindow.ts`.

## Rules

- All math is in physical pixels and on the outer window rect. On Windows an undecorated transparent
  window has an invisible frame (outer = inner + 4 px at scale 1.0). `setPosition` moves the outer rect,
  `setSize` sets the inner size, so the frame (`outerSize - innerSize`) is added to every placement.
- The bottom-right corner of the outer rect is the anchor. It is cached while the bubble grows and shrinks
  and reset when the user drags the bubble.
- The anchor is clamped into the work area of the monitor under it (`monitorFromPoint`), so the bubble and
  every card or panel stay inside the work area on all four sides. The target size uses that monitor's scale.
- Resize calls run one at a time (promise queue). Before this, overlapping ResizeObserver calls could
  apply the position of one call with the size of another.
- `create_bubble` places the hidden window after build with `set_position` in physical pixels from the
  primary monitor work area, minus the outer size and a 24 px (logical) margin.

## Check

With the app running (`npm run tauri dev` in `desktop/`), print the window rects, hidden ones included,
with a `GetWindowRect` script. The hidden bubble must end at work area right - 24 and bottom - 24.
