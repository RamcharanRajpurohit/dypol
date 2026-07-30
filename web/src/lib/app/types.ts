export type Route =
  | "dashboard"
  | "leaderboard"
  | "repos"
  | "repo-detail"
  | "ask"
  | "digest"
  | "alerts"
  | "activity"
  | "settings"
  | "profile";

export type AvatarColor = 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7;
export type Status = "ok" | "hot" | "stuck" | "neutral";

export interface Dev {
  rank: string;
  name: string;
  handle: string;
  role: string;
  avatar: string;
  color: AvatarColor;
  score: number;
  impact: number;
  quality: number;
  collab: number;
  consist: number;
  week: string;
  sparkD: string;
  delta: string;
}

export interface Repo {
  name: string;
  status: Status;
  openPRs: number;
  sum: string;
  spark: ReadonlyArray<number>;
}

export interface Contributor {
  rank: string;
  name: string;
  score: number;
  color: AvatarColor;
  avatar: string;
  delta: string;
  spark: string;
}

export interface ActivityEvent {
  who: string;
  color: AvatarColor;
  avatar: string;
  what: string;
  detail: string;
  when: string;
}

export interface AskSourceItem {
  t: string;
  d: string;
}

export interface AskSourceGroup {
  kind: string;
  items: ReadonlyArray<AskSourceItem>;
}

export interface AskAnswer {
  tools: ReadonlyArray<string>;
  answer: () => string;
  sources: ReadonlyArray<AskSourceGroup>;
  followups: ReadonlyArray<string>;
}

export interface ConversationLink {
  label: string;
  question?: string;
}

export interface ConversationBucket {
  label: string;
  items: ReadonlyArray<ConversationLink>;
}
