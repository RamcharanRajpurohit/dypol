interface Props {
  d: string;
  width?: number;
  height?: number;
}

function getEndY(d: string): number {
  const lastSegment = d.split("L").slice(-1)[0]?.trim() ?? "";
  const parts = lastSegment.split(/\s+/);
  const y = parts[1];
  const parsed = y ? parseFloat(y) : Number.NaN;
  return Number.isFinite(parsed) ? parsed : 10;
}

export function Sparkline({ d, width = 60, height = 20 }: Props) {
  const cy = getEndY(d);
  return (
    <svg className="spark" width={width} height={height} viewBox={`0 0 ${width} ${height}`}>
      <path d={d} />
      <circle cx={width - 4} cy={cy} r={1.6} />
    </svg>
  );
}
