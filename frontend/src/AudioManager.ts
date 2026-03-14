/**
 * AudioManager.ts — captures microphone audio as raw PCM via an AudioWorklet
 * and forwards chunks to a callback (to be sent over WebSocket to the backend).
 *
 * The Gemini Live API expects 16-bit PCM at 16 000 Hz mono.
 */

const WORKLET_CODE = `
class PcmCaptureProcessor extends AudioWorkletProcessor {
  process(inputs) {
    const input = inputs[0];
    if (!input || !input[0]) return true;
    const float32 = input[0];
    // Convert Float32 → Int16
    const int16 = new Int16Array(float32.length);
    for (let i = 0; i < float32.length; i++) {
      const s = Math.max(-1, Math.min(1, float32[i]));
      int16[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
    }
    this.port.postMessage(int16.buffer, [int16.buffer]);
    return true;
  }
}
registerProcessor('pcm-capture-processor', PcmCaptureProcessor);
`

export class AudioManager {
  private onPcm: (chunk: Uint8Array) => void
  private audioContext: AudioContext | null = null
  private workletNode: AudioWorkletNode | null = null
  private sourceNode: MediaStreamAudioSourceNode | null = null
  private stream: MediaStream | null = null
  private workletBlobUrl: string | null = null

  constructor(onPcm: (chunk: Uint8Array) => void) {
    this.onPcm = onPcm
  }

  async start(): Promise<void> {
    // Request microphone
    this.stream = await navigator.mediaDevices.getUserMedia({ audio: true, video: false })

    // Create AudioContext resampled to 16 kHz
    this.audioContext = new AudioContext({ sampleRate: 16000 })

    // Create a Blob URL for the worklet module
    const blob = new Blob([WORKLET_CODE], { type: 'application/javascript' })
    this.workletBlobUrl = URL.createObjectURL(blob)

    await this.audioContext.audioWorklet.addModule(this.workletBlobUrl)

    this.workletNode = new AudioWorkletNode(this.audioContext, 'pcm-capture-processor')
    this.workletNode.port.onmessage = (event: MessageEvent<ArrayBuffer>) => {
      this.onPcm(new Uint8Array(event.data))
    }

    this.sourceNode = this.audioContext.createMediaStreamSource(this.stream)
    this.sourceNode.connect(this.workletNode)
    this.workletNode.connect(this.audioContext.destination)
  }

  stop(): void {
    this.sourceNode?.disconnect()
    this.workletNode?.disconnect()
    this.stream?.getTracks().forEach((t) => t.stop())
    this.audioContext?.close().catch(() => undefined)
    if (this.workletBlobUrl) URL.revokeObjectURL(this.workletBlobUrl)
    this.audioContext = null
    this.workletNode = null
    this.sourceNode = null
    this.stream = null
    this.workletBlobUrl = null
  }
}
