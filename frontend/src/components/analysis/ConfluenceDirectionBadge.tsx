import { ArrowDown, ArrowUp, Minus } from "lucide-react";
import { Badge } from "@/components/ui/Badge";
import { cn } from "@/lib/utils";

type Direction = "long" | "short" | "mixed";

interface Props {
  direction: Direction;
  score: number; // 0-100
  className?: string;
}

/**
 * Direction badge with confidence gate:
 * - < 60: neutralized → "观望"
 * - 60–74: strong signal
 * - ≥ 75: extremely strong signal
 */
export function ConfluenceDirectionBadge({ direction, score, className }: Props) {
  if (direction === "long") {
    return (
      <Badge tone="bull" className={cn("gap-1", className)}>
        <ArrowUp className="w-3 h-3" />
        做多{score >= 75 ? "极强" : score >= 60 ? "强信号" : ""}
      </Badge>
    );
  }
  if (direction === "short") {
    return (
      <Badge tone="bear" className={cn("gap-1", className)}>
        <ArrowDown className="w-3 h-3" />
        做空{score >= 75 ? "极强" : score >= 60 ? "强信号" : ""}
      </Badge>
    );
  }
  return (
    <Badge tone="warning" className={cn("gap-1", className)}>
      <Minus className="w-3 h-3" />
      观望
    </Badge>
  );
}
