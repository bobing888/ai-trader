/**
 * 用户偏好管理 — K 线指标/形态选择
 *
 * 持久化优先级：
 * 1. 后端 Redis（X-User-Id 隔离，多端同步）— 走 PUT/GET /api/preferences
 * 2. localStorage 兜底（后端 503 时降级）
 *
 * anonymous user_id 在首次访问时生成并保存在 localStorage.uuid_user_id
 */

const USER_ID_KEY = "ai_trader_user_id";

export interface IndicatorPref {
  enabled: boolean;
  params: Record<string, number | string | boolean>;
}

export interface ChartPreferences {
  indicators: Record<string, IndicatorPref>;
}

const DEFAULT_PREFS: ChartPreferences = {
  indicators: {
    // 主图均线（用户重点要求多周期）
    ma5: { enabled: false, params: { length: 5 } },
    ma10: { enabled: false, params: { length: 10 } },
    ma20: { enabled: true, params: { length: 20 } },
    ma30: { enabled: true, params: { length: 30 } },
    ma60: { enabled: false, params: { length: 60 } },
    ema12: { enabled: false, params: { length: 12 } },
    ema26: { enabled: false, params: { length: 26 } },
    ema50: { enabled: true, params: { length: 50 } },
    // 完整布林带（3 条线）
    boll: { enabled: true, params: { length: 20, mult: 2.0 } },
    // VWAP
    vwap: { enabled: false, params: {} },
    // 副图指标
    rsi: { enabled: true, params: { length: 14 } },
    rsi6: { enabled: false, params: { length: 6 } },
    rsi24: { enabled: false, params: { length: 24 } },
    macd: { enabled: true, params: { fast: 12, slow: 26, signal: 9 } },
    kdj: { enabled: true, params: { length: 9 } },
    obv: { enabled: true, params: {} },
    stoch: { enabled: false, params: { k: 14, d: 3 } },
    cci: { enabled: false, params: { length: 20 } },
    wr: { enabled: false, params: { length: 14 } },
    mfi: { enabled: false, params: { length: 14 } },
    adx: { enabled: false, params: { length: 14 } },
    atr: { enabled: false, params: { length: 14 } },
    // 高级趋势
    sar: { enabled: false, params: { step: 0.02, max: 0.2 } },
    supertrend: { enabled: false, params: { length: 10, mult: 3.0 } },
    keltner: { enabled: false, params: { length: 20, mult: 2.0 } },
    ichimoku: { enabled: false, params: {} },
  },
};

function getUserId(): string {
  let uid = localStorage.getItem(USER_ID_KEY);
  if (!uid) {
    uid = `anon-${Date.now()}-${Math.random().toString(36).substring(2, 12)}`;
    localStorage.setItem(USER_ID_KEY, uid);
  }
  return uid;
}

const LOCAL_FALLBACK_KEY = "ai_trader_prefs_local";

function loadLocalFallback(): ChartPreferences {
  try {
    const raw = localStorage.getItem(LOCAL_FALLBACK_KEY);
    if (raw) return JSON.parse(raw) as ChartPreferences;
  } catch {
    /* ignore */
  }
  return DEFAULT_PREFS;
}

function saveLocalFallback(prefs: ChartPreferences): void {
  try {
    localStorage.setItem(LOCAL_FALLBACK_KEY, JSON.stringify(prefs));
  } catch {
    /* ignore */
  }
}

export async function loadPreferences(): Promise<ChartPreferences> {
  const uid = getUserId();
  try {
    const res = await fetch("/api/preferences", {
      headers: { "X-User-Id": uid },
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    return data.preferences as ChartPreferences;
  } catch {
    // 后端不可用时回退到 localStorage
    return loadLocalFallback();
  }
}

export async function savePreferences(prefs: ChartPreferences): Promise<boolean> {
  const uid = getUserId();
  // 永远保存到 localStorage 兜底
  saveLocalFallback(prefs);
  try {
    const res = await fetch("/api/preferences", {
      method: "PUT",
      headers: { "Content-Type": "application/json", "X-User-Id": uid },
      body: JSON.stringify(prefs),
    });
    return res.ok;
  } catch {
    return false;
  }
}

export async function resetPreferences(): Promise<ChartPreferences> {
  const uid = getUserId();
  try {
    const res = await fetch("/api/preferences/reset", {
      method: "POST",
      headers: { "X-User-Id": uid },
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    saveLocalFallback(data.preferences);
    return data.preferences;
  } catch {
    saveLocalFallback(DEFAULT_PREFS);
    return DEFAULT_PREFS;
  }
}

export function getUserIdForDebug(): string {
  return getUserId();
}
