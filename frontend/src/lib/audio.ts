/**
 * audio.ts — D5 Web Audio alerts for high/medium quality trading signals.
 *
 * Generates short synthesized tones (no audio files needed):
 *   - high quality  →  ascending C-E-G chord (3 tones, 150ms each)
 *   - medium quality → single mid-tone ping
 *
 * Browser notification API used for off-screen alerts.
 *
 * Pattern reference: binance_futures_bot (audio alert on signal), freqtrade tg plugin.
 */

export type AudioTone = "high" | "medium";

let _audioCtx: AudioContext | null = null;

function getAudioContext(): AudioContext {
  if (!_audioCtx) {
    _audioCtx = new AudioContext();
  }
  return _audioCtx;
}

export function playSignalAlert(tone: AudioTone): void {
  try {
    const ctx = getAudioContext();
    // Resume context if suspended (autoplay policy)
    if (ctx.state === "suspended") {
      ctx.resume();
    }

    if (tone === "high") {
      // C-E-G ascending chord (C5=523Hz, E5=659Hz, G5=784Hz)
      _playTone(ctx, 523, 0.0, 0.15, 0.15);
      _playTone(ctx, 659, 0.0, 0.15, 0.10);
      _playTone(ctx, 784, 0.0, 0.15, 0.08);
    } else {
      // Single A4 ping (440Hz)
      _playTone(ctx, 440, 0.0, 0.12, 0.08);
    }
  } catch {
    // Silent fail — no audio support or blocked
  }
}

function _playTone(
  ctx: AudioContext,
  freq: number,
  delay_s: number,
  duration_s: number,
  gain: number,
): void {
  const osc = ctx.createOscillator();
  const gainNode = ctx.createGain();

  osc.connect(gainNode);
  gainNode.connect(ctx.destination);

  osc.type = "sine";
  osc.frequency.setValueAtTime(freq, ctx.currentTime + delay_s);

  // ADSR envelope
  gainNode.gain.setValueAtTime(0, ctx.currentTime + delay_s);
  gainNode.gain.linearRampToValueAtTime(gain, ctx.currentTime + delay_s + 0.01);
  gainNode.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + delay_s + duration_s);

  osc.start(ctx.currentTime + delay_s);
  osc.stop(ctx.currentTime + delay_s + duration_s + 0.01);
}

// ─── Browser notification ─────────────────────────────────────────────────────

export interface NotificationPayload {
  title: string;
  body: string;
  icon?: string;
}

/** Ask browser permission + fire a native OS notification. */
export async function sendBrowserNotification(payload: NotificationPayload): Promise<void> {
  if (!("Notification" in window)) return;

  if (Notification.permission === "default") {
    await Notification.requestPermission();
  }

  if (Notification.permission !== "granted") return;

  try {
    new Notification(payload.title, {
      body: payload.body,
      icon: payload.icon ?? "/favicon.ico",
      tag: "ai-trader-signal",
    });
  } catch {
    // Safari sometimes throws on Notification constructor
  }
}

/** Format a signal alert into a human-readable notification. */
export function formatSignalNotification(opts: {
  pair: string;
  direction: "long" | "short";
  quality: "high" | "medium";
  entry_levels: Array<{ price: number; size_pct: number; label: string }>;
  stop_loss_price: number | null;
  take_profit_1_price: number | null;
  atr: number | null;
}): NotificationPayload {
  const dir = opts.direction === "long" ? "做多 ↑" : "做空 ↓";
  const quality = opts.quality === "high" ? "高质" : "中质";
  const levels = opts.entry_levels
    .slice(0, 2)
    .map((l) => `${l.label} @ ${l.price.toFixed(2)} (${Math.round(l.size_pct * 100)}%)`)
    .join(", ");

  const body = [
    `${dir} | ${quality} | ATR ${opts.atr?.toFixed(4) ?? "—"}`,
    levels ? `入场: ${levels}` : null,
    opts.stop_loss_price ? `止损: ${opts.stop_loss_price.toFixed(2)}` : null,
    opts.take_profit_1_price ? `TP1: ${opts.take_profit_1_price.toFixed(2)}` : null,
  ]
    .filter(Boolean)
    .join("\n");

  return {
    title: `${opts.pair} 新推荐信号`,
    body,
  };
}
