// Sutradhar browser voice client (M1).
//
// Captures the mic via an AudioWorklet, downsamples to 16 kHz mono int16, and
// streams binary frames over a WebSocket to /ws. Receives 24 kHz int16 PCM from
// the agent and plays it back gaplessly. Half-duplex: talk, pause, the agent
// detects your endpoint and replies.

const SEND_RATE = 16000; // server expects 16 kHz mono int16
const RECV_RATE = 24000; // server sends 24 kHz mono int16

const els = {};
let ctx = null;
let ws = null;
let workletNode = null;
let micStream = null;
let sourceNode = null;
let playhead = 0; // next scheduled playback time
let running = false;

const log = (msg) => {
  const el = els.log;
  el.textContent += `${new Date().toLocaleTimeString()}  ${msg}\n`;
  el.scrollTop = el.scrollHeight;
};

function setStatus(text, on) {
  els.status.textContent = text;
  els.status.style.color = on ? "#3fb950" : "#7c8aa0";
}

// Linear-interpolation resample of a Float32 mono buffer.
function resample(input, srcRate, dstRate) {
  if (srcRate === dstRate) return input;
  const ratio = srcRate / dstRate;
  const outLen = Math.floor(input.length / ratio);
  const out = new Float32Array(outLen);
  for (let i = 0; i < outLen; i++) {
    const pos = i * ratio;
    const idx = Math.floor(pos);
    const frac = pos - idx;
    const a = input[idx] || 0;
    const b = input[idx + 1] !== undefined ? input[idx + 1] : a;
    out[i] = a + (b - a) * frac;
  }
  return out;
}

function floatToInt16(float32) {
  const out = new Int16Array(float32.length);
  for (let i = 0; i < float32.length; i++) {
    const s = Math.max(-1, Math.min(1, float32[i]));
    out[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
  }
  return out;
}

function int16ToFloat(int16) {
  const out = new Float32Array(int16.length);
  for (let i = 0; i < int16.length; i++) out[i] = int16[i] / 0x8000;
  return out;
}

function playPcm(int16) {
  const float = int16ToFloat(int16);
  const buf = ctx.createBuffer(1, float.length, RECV_RATE);
  buf.copyToChannel(float, 0);
  const src = ctx.createBufferSource();
  src.buffer = buf;
  src.connect(ctx.destination);
  const now = ctx.currentTime;
  if (playhead < now) playhead = now + 0.05; // small jitter buffer
  src.start(playhead);
  playhead += buf.duration;
}

async function start() {
  if (running) return;
  ctx = new (window.AudioContext || window.webkitAudioContext)();
  await ctx.audioWorklet.addModule("./worklet.js");

  micStream = await navigator.mediaDevices.getUserMedia({
    audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true },
  });

  const proto = location.protocol === "https:" ? "wss" : "ws";
  ws = new WebSocket(`${proto}://${location.host}/ws`);
  ws.binaryType = "arraybuffer";

  ws.onopen = () => {
    setStatus("connected — talk now", true);
    log("WebSocket open. Streaming mic at 16 kHz.");
  };
  ws.onmessage = (ev) => {
    if (typeof ev.data === "string") {
      const msg = JSON.parse(ev.data);
      log(`event: ${msg.event}`);
      if (msg.event === "barge_in") playhead = 0; // drop queued audio (M2)
      return;
    }
    playPcm(new Int16Array(ev.data));
  };
  ws.onclose = () => {
    setStatus("disconnected", false);
    log("WebSocket closed.");
    stop();
  };
  ws.onerror = () => log("WebSocket error.");

  sourceNode = ctx.createMediaStreamSource(micStream);
  workletNode = new AudioWorkletNode(ctx, "capture-processor");
  workletNode.port.onmessage = (e) => {
    if (!ws || ws.readyState !== WebSocket.OPEN) return;
    const down = resample(e.data, ctx.sampleRate, SEND_RATE);
    ws.send(floatToInt16(down).buffer);
  };
  sourceNode.connect(workletNode);
  // Do not connect the worklet to destination (avoid echo); it still runs.

  running = true;
  els.talk.textContent = "Stop";
  setStatus("connecting…", false);
}

function stop() {
  running = false;
  els.talk.textContent = "Start talking";
  if (workletNode) workletNode.disconnect();
  if (sourceNode) sourceNode.disconnect();
  if (micStream) micStream.getTracks().forEach((t) => t.stop());
  if (ws && ws.readyState === WebSocket.OPEN) ws.close();
  workletNode = sourceNode = micStream = ws = null;
}

window.addEventListener("DOMContentLoaded", () => {
  els.talk = document.getElementById("talk");
  els.status = document.getElementById("status");
  els.log = document.getElementById("log");
  els.talk.disabled = false;
  els.talk.addEventListener("click", () => (running ? stop() : start().catch((e) => log("error: " + e.message))));
  log("Client loaded. Click Start talking and allow the microphone.");
});
