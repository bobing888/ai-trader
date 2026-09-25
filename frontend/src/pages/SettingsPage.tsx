import { useState } from "react";
import { useTranslation } from "react-i18next";
import {
  Globe,
  Palette,
  Bell,
  TrendingUp,
  Database,
  Shield,
  Zap,
  ExternalLink,
  Github,
  Info,
  Check,
  ChevronDown,
} from "lucide-react";

import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { SettingRow } from "@/components/ui/SettingRow";
import { Toggle } from "@/components/ui/Toggle";
import { useToast } from "@/components/ui/Toast";
import { useTheme } from "@/components/ui/ThemeToggle";
import { cn } from "@/lib/utils";

const LANGUAGES = [
  { code: "zh-CN", label: "中文", flag: "🇨🇳" },
  { code: "en", label: "English", flag: "🇺🇸" },
] as const;

type LangCode = (typeof LANGUAGES)[number]["code"];

export function SettingsPage() {
  const { t, i18n } = useTranslation();
  const toast = useToast();
  const { theme, setTheme } = useTheme();

  const [lang, setLang] = useState<LangCode>((i18n.language as LangCode) ?? "zh-CN");
  const [notifications, setNotifications] = useState({
    newSignals: true,
    tradeClose: true,
    dailyReport: false,
    systemAlerts: true,
  });
  const [tradingPrefs, setTradingPrefs] = useState({
    confirmBeforeTrade: true,
    soundEffects: false,
    autoRefresh: true,
  });
  const [defaultTimeframe, setDefaultTimeframe] = useState("15m");
  const [defaultPair, setDefaultPair] = useState("BTCUSDT");

  const switchLang = (code: LangCode) => {
    setLang(code);
    void i18n.changeLanguage(code);
    localStorage.setItem("language", code);
    toast.success("语言已切换", `已切换到 ${LANGUAGES.find((l) => l.code === code)?.label}`);
  };

  const toggleTheme = () => {
    const next = theme === "dark" ? "light" : "dark";
    setTheme(next);
    toast.info(`已切换到${next === "dark" ? "深色" : "浅色"}模式`);
  };

  return (
    <div className="flex flex-col gap-6 max-w-3xl">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-semibold tracking-tight text-text-primary">
          {t("nav.settings")}
        </h1>
        <p className="text-sm text-text-secondary mt-1">个性化你的交易助手体验</p>
      </div>

      {/* Appearance */}
      <SettingsGroup title="外观" description="主题、显示、动画">
        <SettingRow
          icon={<Palette className="w-4 h-4" />}
          iconTone="accent"
          title="主题"
          description="深色护眼，浅色更适合白天长时间使用"
          meta={theme === "dark" ? "深色" : "浅色"}
          control={<Toggle checked={theme === "dark"} onChange={toggleTheme} label="Theme" />}
          noDivider
        />
      </SettingsGroup>

      {/* Language */}
      <SettingsGroup title="语言" description="界面与通知语言">
        <SettingRow
          icon={<Globe className="w-4 h-4" />}
          iconTone="info"
          title="界面语言"
          description="切换后立即生效，保存到本地"
          noDivider
        />
        <div className="grid grid-cols-2 gap-2 pt-3">
          {LANGUAGES.map((l) => (
            <button
              key={l.code}
              onClick={() => switchLang(l.code)}
              data-testid={`lang-${l.code}`}
              className={cn(
                "flex items-center justify-between gap-3 h-12 px-4 rounded-xl",
                "border transition-all duration-150 active:scale-[0.98]",
                lang === l.code
                  ? "bg-accent/10 border-accent/40 shadow-[0_0_0_1px_rgba(204,255,0,0.2)]"
                  : "bg-bg-tertiary border-[rgba(255,240,220,0.06)] hover:border-[rgba(255,240,220,0.16)]",
              )}
            >
              <div className="flex items-center gap-2">
                <span className="text-lg leading-none">{l.flag}</span>
                <span
                  className={cn(
                    "text-sm font-medium",
                    lang === l.code ? "text-text-primary" : "text-text-secondary",
                  )}
                >
                  {l.label}
                </span>
              </div>
              {lang === l.code && (
                <span className="w-4 h-4 rounded-full bg-accent flex items-center justify-center">
                  <Check className="w-2.5 h-2.5 text-[#140c0c]" strokeWidth={3} />
                </span>
              )}
            </button>
          ))}
        </div>
      </SettingsGroup>

      {/* Notifications */}
      <SettingsGroup title="通知" description="信号提醒与每日报告">
        <SettingRow
          icon={<Bell className="w-4 h-4" />}
          iconTone="warning"
          title="新信号提醒"
          description="W2 推荐引擎上线时收到新做多做空信号"
          control={
            <Toggle
              checked={notifications.newSignals}
              onChange={(v) => setNotifications((p) => ({ ...p, newSignals: v }))}
            />
          }
        />
        <SettingRow
          icon={<TrendingUp className="w-4 h-4" />}
          iconTone="bull"
          title="交易完成通知"
          description="持仓平仓时推送结果"
          control={
            <Toggle
              checked={notifications.tradeClose}
              onChange={(v) => setNotifications((p) => ({ ...p, tradeClose: v }))}
            />
          }
        />
        <SettingRow
          icon={<Database className="w-4 h-4" />}
          iconTone="info"
          title="每日报告"
          description="每天 8:00 推送昨日盈亏与胜率"
          control={
            <Toggle
              checked={notifications.dailyReport}
              onChange={(v) => setNotifications((p) => ({ ...p, dailyReport: v }))}
            />
          }
        />
        <SettingRow
          icon={<Shield className="w-4 h-4" />}
          iconTone="bear"
          title="系统告警"
          description="API 异常 / 服务下线等紧急通知"
          noDivider
          control={
            <Toggle
              checked={notifications.systemAlerts}
              onChange={(v) => setNotifications((p) => ({ ...p, systemAlerts: v }))}
            />
          }
        />
      </SettingsGroup>

      {/* Trading */}
      <SettingsGroup title="交易" description="默认参数与下单行为">
        <SettingRow
          icon={<Zap className="w-4 h-4" />}
          iconTone="accent"
          title="下单前确认"
          description="避免误触，自动执行前弹出确认"
          control={
            <Toggle
              checked={tradingPrefs.confirmBeforeTrade}
              onChange={(v) => setTradingPrefs((p) => ({ ...p, confirmBeforeTrade: v }))}
            />
          }
        />
        <SettingRow
          icon={<Bell className="w-4 h-4" />}
          iconTone="info"
          title="交易音效"
          description="成交时播放提示音"
          control={
            <Toggle
              checked={tradingPrefs.soundEffects}
              onChange={(v) => setTradingPrefs((p) => ({ ...p, soundEffects: v }))}
            />
          }
        />
        <SettingRow
          icon={<TrendingUp className="w-4 h-4" />}
          iconTone="bull"
          title="自动刷新"
          description="K 线与持仓每 5 秒自动刷新"
          noDivider
          control={
            <Toggle
              checked={tradingPrefs.autoRefresh}
              onChange={(v) => setTradingPrefs((p) => ({ ...p, autoRefresh: v }))}
            />
          }
        />
      </SettingsGroup>

      {/* Defaults */}
      <SettingsGroup title="默认值" description="进入页面时的初始选择">
        <SettingRow
          icon={<TrendingUp className="w-4 h-4" />}
          iconTone="accent"
          title="默认交易对"
          description="打开 K 线页时显示的币种"
          control={<Select value={defaultPair} onChange={setDefaultPair} options={["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT"]} />}
        />
        <SettingRow
          icon={<Database className="w-4 h-4" />}
          iconTone="info"
          title="默认时间周期"
          description="K 线页与推荐单的时间粒度"
          noDivider
          control={<Select value={defaultTimeframe} onChange={setDefaultTimeframe} options={["1m", "5m", "15m", "1h", "4h", "1d"]} />}
        />
      </SettingsGroup>

      {/* About */}
      <SettingsGroup title="关于" description="版本、链接与项目信息">
        <SettingRow
          icon={<Info className="w-4 h-4" />}
          iconTone="default"
          title="AI 交易助手"
          description="多策略加密货币自动交易系统"
          meta={<Badge tone="muted">v0.1.0</Badge>}
        />
        <SettingRow
          icon={<Github className="w-4 h-4" />}
          iconTone="default"
          title="源代码"
          description="ai-trader 在 GitHub 开源"
          control={
            <a
              href="#"
              className="inline-flex items-center gap-1 text-xs font-medium text-text-secondary hover:text-accent transition-colors"
              onClick={(e) => e.preventDefault()}
            >
              查看仓库
              <ExternalLink className="w-3 h-3" />
            </a>
          }
        />
        <SettingRow
          icon={<Shield className="w-4 h-4" />}
          iconTone="bull"
          title="隐私"
          description="所有设置保存在本地，不上传服务器"
          noDivider
        />
      </SettingsGroup>
    </div>
  );
}

function SettingsGroup({
  title,
  description,
  children,
}: {
  title: string;
  description?: string;
  children: React.ReactNode;
}) {
  return (
    <Card className="overflow-hidden">
      <div className="px-5 pt-4 pb-2 border-b border-[rgba(255,240,220,0.06)]">
        <h2 className="text-sm font-semibold text-text-primary">{title}</h2>
        {description && <p className="text-[11px] text-text-tertiary mt-0.5">{description}</p>}
      </div>
      <div className="px-5">{children}</div>
    </Card>
  );
}

interface SelectProps {
  value: string;
  onChange: (v: string) => void;
  options: string[];
}

function Select({ value, onChange, options }: SelectProps) {
  return (
    <div className="relative">
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className={cn(
          "appearance-none h-8 pl-3 pr-8 rounded-full",
          "bg-bg-tertiary border border-[rgba(255,240,220,0.08)]",
          "text-xs font-medium text-text-primary",
          "hover:border-[rgba(255,240,220,0.16)] focus:outline-none focus:border-accent/40",
          "cursor-pointer transition-colors",
        )}
      >
        {options.map((o) => (
          <option key={o} value={o}>
            {o}
          </option>
        ))}
      </select>
      <ChevronDown className="absolute right-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-text-tertiary pointer-events-none" />
    </div>
  );
}
