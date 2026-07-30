import type { AvatarColor } from "@/lib/app/types";
import { cn } from "@/lib/cn";

type Size = "sm" | "md" | "lg";

interface Props {
  initials: string;
  color: AvatarColor;
  size?: Size;
  className?: string;
  rounded?: "full" | "md";
  style?: React.CSSProperties;
}

export function Avatar({ initials, color, size = "md", className, rounded = "full", style }: Props) {
  return (
    <span
      className={cn("avatar", `color-${color}`, size, className)}
      style={{
        ...(rounded === "md" ? { borderRadius: 6, width: 26, height: 26 } : null),
        ...style,
      }}
    >
      {initials}
    </span>
  );
}
