import type { SVGProps } from "react";

type IconProps = SVGProps<SVGSVGElement>;

const baseStroke: Partial<IconProps> = {
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 1.5,
};

export function DashboardIcon(props: IconProps) {
  return (
    <svg className="ico" viewBox="0 0 16 16" {...baseStroke} {...props}>
      <path d="M2 8l3-3 3 3 3-4 3 3" />
      <path d="M2 13h12" />
    </svg>
  );
}

export function DigestIcon(props: IconProps) {
  return (
    <svg className="ico" viewBox="0 0 16 16" {...baseStroke} {...props}>
      <rect x={2.5} y={2.5} width={11} height={11} rx={1} />
      <path d="M5 6h6M5 9h6M5 12h4" />
    </svg>
  );
}

export function BellIcon(props: IconProps) {
  return (
    <svg className="ico" viewBox="0 0 16 16" {...baseStroke} {...props}>
      <path d="M3 11h10l-1.5-2V6a3.5 3.5 0 0 0-7 0v3L3 11z" />
      <path d="M7 13h2" />
    </svg>
  );
}

export function ChatIcon(props: IconProps) {
  return (
    <svg className="ico" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth={1.6} {...props}>
      <path d="M2 6.5C2 4 4 2.5 8 2.5s6 1.5 6 4-2 4-6 4l-3 2.5v-3C3 9.5 2 8.2 2 6.5z" />
    </svg>
  );
}

export function BarsIcon(props: IconProps) {
  return (
    <svg className="ico" viewBox="0 0 16 16" {...baseStroke} {...props}>
      <path d="M3 13V8M8 13V4M13 13V10" />
    </svg>
  );
}

export function PeopleIcon(props: IconProps) {
  return (
    <svg className="ico" viewBox="0 0 16 16" {...baseStroke} {...props}>
      <circle cx={6} cy={6} r={2.5} />
      <path d="M2 13c0-2 2-3.5 4-3.5s4 1.5 4 3.5" />
      <circle cx={11} cy={5} r={1.8} />
      <path d="M9 12c1-1.5 2.5-2 4-2s3 .5 3 2" />
    </svg>
  );
}

export function RepoIcon(props: IconProps) {
  return (
    <svg className="ico" viewBox="0 0 16 16" {...baseStroke} {...props}>
      <path d="M3 3h7l3 3v7H3z" />
      <path d="M5 7h6M5 10h4" />
    </svg>
  );
}

export function ClockIcon(props: IconProps) {
  return (
    <svg className="ico" viewBox="0 0 16 16" {...baseStroke} {...props}>
      <circle cx={8} cy={8} r={6} />
      <path d="M8 4v4l3 2" />
    </svg>
  );
}

export function SettingsIcon(props: IconProps) {
  return (
    <svg className="ico" viewBox="0 0 16 16" {...baseStroke} {...props}>
      <circle cx={8} cy={8} r={2} />
      <path d="M8 2v1.5M8 12.5V14M2 8h1.5M12.5 8H14M3.8 3.8l1 1M11.2 11.2l1 1M3.8 12.2l1-1M11.2 4.8l1-1" />
    </svg>
  );
}

export function PlusIcon(props: IconProps) {
  return (
    <svg width={10} height={10} viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth={1.7} {...props}>
      <path d="M8 3v10M3 8h10" />
    </svg>
  );
}

export function ChevronDownIcon(props: IconProps) {
  return (
    <svg width={11} height={11} viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth={1.5} {...props}>
      <path d="M4 6l4 4 4-4" />
    </svg>
  );
}

export function ChevronUpIcon(props: IconProps) {
  return (
    <svg width={11} height={11} viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth={1.5} {...props}>
      <path d="M4 10l4-4 4 4" />
    </svg>
  );
}

export function SearchIcon(props: IconProps) {
  return (
    <svg width={13} height={13} viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth={1.5} {...props}>
      <circle cx={7} cy={7} r={4.5} />
      <path d="M11 11l3 3" />
    </svg>
  );
}

export function CalendarIcon(props: IconProps) {
  return (
    <svg width={11} height={11} viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth={1.5} {...props}>
      <rect x={2.5} y={3.5} width={11} height={10} rx={1} />
      <path d="M5 2v3M11 2v3M2.5 7h11" />
    </svg>
  );
}

export function ExportIcon(props: IconProps) {
  return (
    <svg width={13} height={13} viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth={1.5} {...props}>
      <path d="M3 8l3-3v2h7v2H6v2L3 8z" />
    </svg>
  );
}

export function ArrowSendIcon(props: IconProps) {
  return (
    <svg width={11} height={11} viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth={1.8} {...props}>
      <path d="M3 8h10M9 4l4 4-4 4" />
    </svg>
  );
}

export function CloseIcon(props: IconProps) {
  return (
    <svg width={14} height={14} viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth={1.7} {...props}>
      <path d="M3 3l10 10M13 3L3 13" />
    </svg>
  );
}

export function MoonIcon(props: IconProps) {
  return (
    <svg width={14} height={14} viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth={1.5} {...props}>
      <path d="M13 9.5A5.5 5.5 0 0 1 6.5 3 5 5 0 1 0 13 9.5z" />
    </svg>
  );
}

export function SunIcon(props: IconProps) {
  return (
    <svg width={14} height={14} viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth={1.5} {...props}>
      <circle cx={8} cy={8} r={3} />
      <path d="M8 1v2M8 13v2M1 8h2M13 8h2M3.5 3.5l1.5 1.5M11 11l1.5 1.5M3.5 12.5l1.5-1.5M11 5l1.5-1.5" />
    </svg>
  );
}
