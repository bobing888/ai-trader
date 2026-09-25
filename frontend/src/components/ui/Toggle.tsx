import { cn } from "@/lib/utils";

export interface ToggleProps {
  checked: boolean;
  onChange: (checked: boolean) => void;
  size?: "sm" | "md";
  disabled?: boolean;
  label?: string;
  "data-testid"?: string;
}

interface ToggleSize {
  trackW: number;
  trackH: number;
  knob: number;
  padding: number;
}

const SIZE: Record<NonNullable<ToggleProps["size"]>, ToggleSize> = {
  sm: { trackW: 34, trackH: 20, knob: 14, padding: 3 },
  md: { trackW: 44, trackH: 26, knob: 20, padding: 3 },
};

export function Toggle({ checked, onChange, size = "md", disabled, label, "data-testid": testId }: ToggleProps) {
  const s = SIZE[size];
  const trackStyle = { width: `${s.trackW}px`, height: `${s.trackH}px` };
  const knobStyle = {
    width: `${s.knob}px`,
    height: `${s.knob}px`,
    transform: `translate(${checked ? s.trackW - s.knob - s.padding : s.padding}px, -50%)`,
  };

  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      disabled={disabled}
      onClick={() => onChange(!checked)}
      style={trackStyle}
      data-testid={testId}
      className={cn(
        "relative shrink-0 rounded-full border transition-colors duration-200",
        "focus:outline-none focus-visible:ring-2 focus-visible:ring-accent/50 focus-visible:ring-offset-2 focus-visible:ring-offset-bg-primary",
        checked
          ? "bg-accent border-accent"
          : "bg-bg-elevated border-[rgba(255,240,220,0.08)]",
        disabled && "opacity-50 cursor-not-allowed",
      )}
    >
      <span
        aria-hidden="true"
        style={knobStyle}
        className={cn(
          "absolute top-1/2 left-0 rounded-full shadow-[0_1px_3px_rgba(0,0,0,0.4)] transition-colors duration-200",
          checked ? "bg-[#140c0c]" : "bg-text-tertiary",
        )}
      />
    </button>
  );
}
