export type Presence = "online" | "busy" | "dnd" | "away" | "brb" | "offline";
export type Role = "owner" | "admin" | "member";
export type ChannelKind = "channel" | "dm";

export interface User {
  id: string;
  email: string;
  name: string;
  title: string | null;
  avatar_color: string | null;
  avatar_url: string | null;
  presence: Presence;
  last_seen_at: string | null;
  created_at: string;
}

export interface Member {
  user: User;
  role: Role;
  joined_at: string;
}

export interface Workspace {
  id: string;
  name: string;
  slug: string;
  created_at: string;
}

export interface Reaction {
  emoji: string;
  count: number;
  user_ids: string[];
  me: boolean;
}

export interface FileRef {
  id: string;
  name: string;
  url: string;
  mime: string;
  size: number;
}

export interface ReplyTo {
  id: string;
  author_name: string;
  body: string;
  deleted: boolean;
}

export interface Message {
  id: string;
  channel_id: string;
  user_id: string;
  author: User;
  body: string;
  kind: "text" | "system";
  parent_id: string | null;
  /** The message this one answers. */
  reply_to_id: string | null;
  /** That message, in the small form a quote needs. */
  reply_to: ReplyTo | null;
  /** True when the reply was written in the channel, so it shows there too. */
  inline: boolean;
  created_at: string;
  edited_at: string | null;
  deleted_at: string | null;
  reply_count: number;
  last_reply_at: string | null;
  pinned: boolean;
  reactions: Reaction[];
  attachments: FileRef[];
}

export interface Channel {
  id: string;
  workspace_id: string;
  name: string;
  topic: string | null;
  purpose: string | null;
  kind: ChannelKind;
  is_private: boolean;
  created_by: string;
  created_at: string;
  member_count: number;
  unread_count: number;
  last_message_at: string | null;
  dm_user: User | null;
  members: User[] | null;
  /** Whether the viewer is in this channel. A public channel stays in the
      workspace's directory after you leave it, so the rail needs to know. */
  is_member: boolean;
}

/* ── organization ──────────────────────────────────────────────────────── */

/** A unit of the organization — a department, a team, a squad. */
export interface OrgUnit {
  id: string;
  workspace_id: string;
  /** The unit above this one; null for a root. */
  parent_id: string | null;
  name: string;
  /** A free label for what the unit is — 부서, 팀, … */
  kind: string;
  description: string;
  position: number;
  created_at: string;
  updated_at: string;
  member_count: number;
  child_count: number;
  /** 0 for a root; every level deeper adds one. */
  depth: number;
  /** The people in this unit. */
  members: User[];
  /** The people appointed as the managers of this unit. */
  managers: User[];
  /** Whether I manage this unit or one of its ancestors. */
  is_manager: boolean;
  /** Whether I may rename, move and delete it and change its roster. */
  can_manage: boolean;
  /** Whether I may appoint managers for it. */
  can_appoint_managers: boolean;
}

/** The organization of a workspace, as the server sees it. */
export interface OrgOverview {
  /** A flat list — the tree is `parent_id` -> `id`. */
  units: OrgUnit[];
  /** The owners and admins of the workspace. */
  admins: Member[];
  /** My own role in this workspace. */
  my_role: Role;
  /** Whether I may appoint and remove workspace admins. */
  can_manage_admins: boolean;
  /** The units I manage. */
  managed_unit_ids: string[];
}

/** What the bootstrap says about the organization — enough to show the rail. */
export interface OrgSummary {
  unit_count: number;
  managed_unit_ids: string[];
}

/** The fields a unit is created or changed with. */
export interface OrgUnitInput {
  name: string;
  parent_id?: string | null;
  kind?: string;
  description?: string;
}

export interface Bootstrap {
  workspace: Workspace;
  channels: Channel[];
  dms: Channel[];
  members: Member[];
  me: User;
  org: OrgSummary;
}

export interface Invite {
  id: string;
  workspace_id: string;
  email: string;
  role: Role;
  token: string;
  created_by: string;
  created_at: string;
  expires_at: string;
}

export type RsvpResponse = "accepted" | "declined" | "tentative";
export type EventResponse = RsvpResponse | "pending";

export interface ScheduleAttendee {
  user: User;
  response: EventResponse;
}

export interface ScheduleEvent {
  id: string;
  workspace_id: string;
  title: string;
  description: string;
  location: string;
  starts_at: string;
  ends_at: string;
  all_day: boolean;
  is_private: boolean;
  created_by: string;
  channel_id: string | null;
  created_at: string;
  updated_at: string;
  attendees: ScheduleAttendee[];
  my_response: EventResponse | null;
}

export interface EventInput {
  title: string;
  description?: string;
  location?: string;
  starts_at: string;
  ends_at: string;
  all_day?: boolean;
  is_private?: boolean;
  channel_id?: string | null;
  attendee_ids?: string[];
}

export interface SearchResult {
  message: Message;
  channel: Channel;
}

/* ── projects and their board ──────────────────────────────────────────── */

export type TaskStatus = "request" | "todo" | "in-progress" | "done";

export interface Project {
  id: string;
  workspace_id: string;
  name: string;
  /** What this project is about — the one line the board shows. */
  description: string;
  purpose: string;
  deliverables: string;
  /** The room where this project is talked about. */
  channel_id: string | null;
  created_by: string;
  is_archived: boolean;
  created_at: string;
  updated_at: string;
  /** The people on the project — the ones who look after it. */
  members: User[];
  /** Whether I am on that roster. */
  is_member: boolean;
  /** How many cards are not finished yet, and how many of them are mine. */
  open_tasks: number;
  my_open_tasks: number;
  /** Every card on the project, and how many of them are done. */
  total_tasks: number;
  done_tasks: number;
  /** The period the project occupies — the first thing due to the last. */
  start_at: string | null;
  end_at: string | null;
}

export interface TaskComment {
  id: string;
  task_id: string;
  user_id: string;
  author: User;
  body: string;
  created_at: string;
}

export interface Task {
  id: string;
  project_id: string;
  title: string;
  description: string;
  status: TaskStatus;
  /** The roadmap this task belongs to, when it belongs to one. */
  roadmap_id: string | null;
  roadmap_name: string | null;
  /** The milestone this task belongs to, when it belongs to one. A card may
      carry a milestone: it says when the work is due. */
  milestone_id: string | null;
  milestone_name: string | null;
  milestone_color: string | null;
  assignee_id: string | null;
  assignee: User | null;
  created_by: string;
  start_at: string | null;
  due_at: string | null;
  position: number;
  created_at: string;
  updated_at: string;
  comments: TaskComment[];
  comment_count: number;
}

export interface ProjectInput {
  name: string;
  description?: string;
  purpose?: string;
  deliverables?: string;
  channel_id?: string | null;
  member_ids?: string[];
}

/** A lane of work inside a project — the tabs above the board. */
export interface Roadmap {
  id: string;
  project_id: string;
  name: string;
  position: number;
  created_by: string;
  created_at: string;
  /** How many tasks hang on this roadmap. */
  task_count: number;
}

export interface TaskInput {
  title: string;
  description?: string;
  status?: TaskStatus;
  assignee_id?: string | null;
  start_at?: string | null;
  due_at?: string | null;
  roadmap_id?: string | null;
  /** The milestone this task hangs on — null clears it. */
  milestone_id?: string | null;
}

/* ── milestones ─────────────────────────────────────────────────────────── */

/**
 * A time-boxed deliverable marker. It is not a lane and not a column: a
 * card may carry a roadmap AND a milestone.
 */
export interface Milestone {
  id: string;
  project_id: string;
  title: string;
  /** ISO datetime — the day the milestone opens. */
  start_at: string;
  /** ISO datetime — the day the milestone closes. */
  end_at: string;
  /** The colour the company chose — a hex, theirs to pick. */
  color: string;
  /** The progress in force: the cards' when they are linked, else the
      slider's. */
  progress: number;
  /** What the slider holds. */
  manual_progress: number;
  description: string;
  /** How many cards hang on this milestone. */
  task_count: number;
  /** How many of them are done. */
  done_count: number;
  /** True when the progress comes from the linked cards. */
  auto_progress: boolean;
  /** The linked card ids. */
  task_ids: string[];
  created_by: string;
  created_at: string;
  updated_at: string;
}

/** The fields a milestone is created or changed with. */
export interface MilestoneInput {
  title: string;
  start_at: string;
  end_at: string;
  color?: string;
  progress?: number;
  description?: string;
  task_ids?: string[];
}

export interface Tokens {
  access_token: string;
  refresh_token: string;
}

export interface Session extends Tokens {
  user: User;
  workspace: Workspace;
}

export interface WsEvent {
  type:
    | "hello"
    | "message.created"
    | "message.updated"
    | "message.deleted"
    | "reaction.updated"
    | "typing"
    | "presence"
    | "user.updated"
    | "channel.created"
    | "channel.updated"
    | "members.changed"
    | "unread"
    | "event.created"
    | "event.updated"
    | "event.deleted"
    | "project.created"
    | "project.updated"
    | "project.deleted"
    | "task.created"
    | "task.updated"
    | "task.deleted"
    | "org.changed"
    | "pong";
  message?: Message;
  message_id?: string;
  channel_id?: string;
  channel?: Channel;
  user_id?: string;
  user?: User;
  name?: string;
  on?: boolean;
  presence?: Presence;
  members?: User[];
  count?: number;
  event?: ScheduleEvent;
  event_id?: string;
  project?: Project;
  project_id?: string;
  task?: Task;
  task_id?: string;
}
