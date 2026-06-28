// AudioWorklet capture processor: forwards mono float32 mic blocks (128 samples
// per quantum at the context sample rate) to the main thread, which downsamples
// to 16 kHz int16 and streams them over the WebSocket.
class CaptureProcessor extends AudioWorkletProcessor {
  process(inputs) {
    const input = inputs[0];
    if (input && input[0] && input[0].length) {
      // Copy — the underlying buffer is reused by the engine after process().
      this.port.postMessage(input[0].slice(0));
    }
    return true; // keep the processor alive
  }
}
registerProcessor("capture-processor", CaptureProcessor);
