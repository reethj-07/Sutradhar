// Sutradhar browser diagnostic client (scaffold placeholder).
//
// M1 implements: capture mic via AudioWorklet, downsample to 16 kHz mono PCM,
// stream frames over a WebSocket to /ws, receive synthesized PCM back and play
// it through an AudioContext, and signal barge-in when the user starts talking.
//
// For M0 this file only logs that the client is loaded so the static page is
// servable and the wiring is obvious.

const log = (msg) => {
  const el = document.getElementById("log");
  el.textContent += `${new Date().toISOString()}  ${msg}\n`;
  el.scrollTop = el.scrollHeight;
};

window.addEventListener("DOMContentLoaded", () => {
  log("Sutradhar diagnostic client loaded (M0 scaffold).");
  log("Voice streaming over WebSocket /ws is implemented in M1.");
});
