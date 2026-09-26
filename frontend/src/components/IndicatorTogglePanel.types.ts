/**
 * 指标 chip 形状 — IndicatorTogglePanel 用。
 *
 * 为什么不放 registry：本文件只描述 chip 渲染需要的字段（id/label/color/overlay/style/hint），
 * registry 文件（lib/indicatorRegistry.ts）描述的是指标计算 / 渲染需要的字段（id/label/color/overlay/extraPlots）。
 * 两边各管一头，避免互相污染。
 *
 * 兼容性：registry 的 IndicatorDef 结构是本类型的子集（registry 没有 style/hint，有 extraPlots），
 * 因此可以把 registry 的 defs 直接当 chip defs 用 — KlinePage.getUnifiedDefs 的类型断言保证了这点。
 */
export interface IndicatorDef {
  id: string;
  label: string;
  /** chip 主题色（hex / var） */
  color: string;
  /** true = 主图叠层；false = 副图面板 */
  overlay: boolean;
  /** BOLL 这种 dashed 样式；副图默认实线 */
  style?: "solid" | "dashed";
  /** 鼠标 hover 提示，可选 */
  hint?: string;
}
