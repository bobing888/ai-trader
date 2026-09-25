// K 线主图指标 (MA/BOLL) 配色常量
// 用户重点关注 MA 系列 (5/10/20/30/60) 与 BOLL (布林带)
// 配色方案：MA 暖色系 (短周期浅色，长周期深色)，BOLL 冷色系 (青/蓝)，与黑色背景高对比
export const MA_BOLL_COLORS = {
  ma5:  "#fef3c7", // warm white — 极短周期，紧贴价
  ma10: "#fbbf24", // amber
  ma20: "#fb923c", // orange
  ma30: "#f43f5e", // rose
  ma60: "#a855f7", // violet
  bollUpper: "rgba(96, 165, 250, 0.85)", // sky blue 虚线
  bollMid:   "#22d3ee",                   // cyan 实线
  bollLower: "rgba(96, 165, 250, 0.85)",
} as const;
