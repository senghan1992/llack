
// ── Presence & Roles ──────────────────────────────────────────

enum Presence {
  online,
  busy,
  dnd,
  away,
  brb,
  offline;

  static Presence fromString(String? val) {
    switch (val) {
      case 'online':
        return Presence.online;
      case 'busy':
        return Presence.busy;
      case 'dnd':
        return Presence.dnd;
      case 'away':
        return Presence.away;
      case 'brb':
        return Presence.brb;
      default:
        return Presence.offline;
    }
  }

  String get apiValue => name;

  String get label {
    switch (this) {
      case Presence.online:
        return '온라인';
      case Presence.busy:
        return '바쁨';
      case Presence.dnd:
        return '방해 금지';
      case Presence.away:
        return '잠시 자리 비움';
      case Presence.brb:
        return '곧 돌아오겠습니다';
      case Presence.offline:
        return '오프라인';
    }
  }
}

enum Role {
  owner,
  admin,
  member;

  static Role fromString(String? val) {
    switch (val) {
      case 'owner':
        return Role.owner;
      case 'admin':
        return Role.admin;
      default:
        return Role.member;
    }
  }

  String get label {
    switch (this) {
      case Role.owner:
        return '소유자';
      case Role.admin:
        return '관리자';
      case Role.member:
        return '멤버';
    }
  }
}

// ── User & Member ─────────────────────────────────────────────

class User {
  final String id;
  final String email;
  final String name;
  final String? title;
  final String? avatarColor;
  final String? avatarUrl;
  final Presence presence;
  final DateTime? lastSeenAt;
  final DateTime? createdAt;

  User({
    required this.id,
    required this.email,
    required this.name,
    this.title,
    this.avatarColor,
    this.avatarUrl,
    this.presence = Presence.offline,
    this.lastSeenAt,
    this.createdAt,
  });

  factory User.fromJson(Map<String, dynamic> json) {
    return User(
      id: json['id'] as String? ?? '',
      email: json['email'] as String? ?? '',
      name: json['name'] as String? ?? '',
      title: json['title'] as String?,
      avatarColor: json['avatar_color'] as String?,
      avatarUrl: json['avatar_url'] as String?,
      presence: Presence.fromString(json['presence'] as String?),
      lastSeenAt: json['last_seen_at'] != null ? DateTime.tryParse(json['last_seen_at'] as String) : null,
      createdAt: json['created_at'] != null ? DateTime.tryParse(json['created_at'] as String) : null,
    );
  }

  Map<String, dynamic> toJson() => {
    'id': id,
    'email': email,
    'name': name,
    'title': title,
    'avatar_color': avatarColor,
    'avatar_url': avatarUrl,
    'presence': presence.apiValue,
  };

  User copyWith({
    String? name,
    String? title,
    String? avatarColor,
    Presence? presence,
  }) {
    return User(
      id: id,
      email: email,
      name: name ?? this.name,
      title: title ?? this.title,
      avatarColor: avatarColor ?? this.avatarColor,
      avatarUrl: avatarUrl,
      presence: presence ?? this.presence,
      lastSeenAt: lastSeenAt,
      createdAt: createdAt,
    );
  }
}

class Member {
  final User user;
  final Role role;
  final DateTime? joinedAt;

  Member({required this.user, required this.role, this.joinedAt});

  factory Member.fromJson(Map<String, dynamic> json) {
    return Member(
      user: User.fromJson(json['user'] as Map<String, dynamic>? ?? json),
      role: Role.fromString(json['role'] as String?),
      joinedAt: json['joined_at'] != null ? DateTime.tryParse(json['joined_at'] as String) : null,
    );
  }
}

class Workspace {
  final String id;
  final String name;
  final String slug;
  final DateTime? createdAt;

  Workspace({required this.id, required this.name, required this.slug, this.createdAt});

  factory Workspace.fromJson(Map<String, dynamic> json) {
    return Workspace(
      id: json['id'] as String? ?? '',
      name: json['name'] as String? ?? '',
      slug: json['slug'] as String? ?? '',
      createdAt: json['created_at'] != null ? DateTime.tryParse(json['created_at'] as String) : null,
    );
  }
}

// ── Messages, Reactions, Attachments ──────────────────────────

class Reaction {
  final String emoji;
  final int count;
  final List<String> userIds;
  final bool me;

  Reaction({
    required this.emoji,
    required this.count,
    required this.userIds,
    required this.me,
  });

  factory Reaction.fromJson(Map<String, dynamic> json) {
    return Reaction(
      emoji: json['emoji'] as String? ?? '',
      count: json['count'] as int? ?? 0,
      userIds: (json['user_ids'] as List<dynamic>?)?.map((e) => e.toString()).toList() ?? [],
      me: json['me'] as bool? ?? false,
    );
  }
}

class FileRef {
  final String id;
  final String name;
  final String url;
  final String mime;
  final int size;

  FileRef({required this.id, required this.name, required this.url, required this.mime, required this.size});

  factory FileRef.fromJson(Map<String, dynamic> json) {
    return FileRef(
      id: json['id'] as String? ?? '',
      name: json['name'] as String? ?? '',
      url: json['url'] as String? ?? '',
      mime: json['mime'] as String? ?? '',
      size: json['size'] as int? ?? 0,
    );
  }
}

class ReplyTo {
  final String id;
  final String authorName;
  final String body;
  final bool deleted;

  ReplyTo({required this.id, required this.authorName, required this.body, required this.deleted});

  factory ReplyTo.fromJson(Map<String, dynamic> json) {
    return ReplyTo(
      id: json['id'] as String? ?? '',
      authorName: json['author_name'] as String? ?? '',
      body: json['body'] as String? ?? '',
      deleted: json['deleted'] as bool? ?? false,
    );
  }
}

class Message {
  final String id;
  final String channelId;
  final String userId;
  final User author;
  final String body;
  final String kind; // "text" | "system"
  final String? parentId;
  final String? replyToId;
  /// 인라인 답글이 참조하는 원본 메시지 요약 (없으면 null).
  final ReplyTo? replyTo;
  final bool inline;
  final DateTime createdAt;
  final DateTime? editedAt;
  final DateTime? deletedAt;
  final int replyCount;
  final DateTime? lastReplyAt;
  final bool pinned;
  final List<Reaction> reactions;
  final List<FileRef> attachments;

  Message({
    required this.id,
    required this.channelId,
    required this.userId,
    required this.author,
    required this.body,
    this.kind = 'text',
    this.parentId,
    this.replyToId,
    this.replyTo,
    this.inline = false,
    required this.createdAt,
    this.editedAt,
    this.deletedAt,
    this.replyCount = 0,
    this.lastReplyAt,
    this.pinned = false,
    this.reactions = const [],
    this.attachments = const [],
  });

  bool get isSystem => kind == 'system';
  bool get isDeleted => deletedAt != null;
  bool get isThreadReply => parentId != null;

  factory Message.fromJson(Map<String, dynamic> json) {
    return Message(
      id: json['id'] as String? ?? '',
      channelId: json['channel_id'] as String? ?? '',
      userId: json['user_id'] as String? ?? '',
      author: User.fromJson(json['author'] as Map<String, dynamic>? ?? {}),
      body: json['body'] as String? ?? '',
      kind: json['kind'] as String? ?? 'text',
      parentId: json['parent_id'] as String?,
      replyToId: json['reply_to_id'] as String?,
      replyTo: json['reply_to'] != null ? ReplyTo.fromJson(json['reply_to'] as Map<String, dynamic>) : null,
      inline: json['inline'] as bool? ?? false,
      createdAt: DateTime.tryParse(json['created_at'] as String? ?? '') ?? DateTime.now(),
      editedAt: json['edited_at'] != null ? DateTime.tryParse(json['edited_at'] as String) : null,
      deletedAt: json['deleted_at'] != null ? DateTime.tryParse(json['deleted_at'] as String) : null,
      replyCount: json['reply_count'] as int? ?? 0,
      lastReplyAt: json['last_reply_at'] != null ? DateTime.tryParse(json['last_reply_at'] as String) : null,
      pinned: json['pinned'] as bool? ?? false,
      reactions: (json['reactions'] as List<dynamic>?)
              ?.map((e) => Reaction.fromJson(e as Map<String, dynamic>))
              .toList() ??
          [],
      attachments: (json['attachments'] as List<dynamic>?)
              ?.map((e) => FileRef.fromJson(e as Map<String, dynamic>))
              .toList() ??
          [],
    );
  }

  Message copyWith({
    String? body,
    DateTime? editedAt,
    DateTime? deletedAt,
    bool? pinned,
    List<Reaction>? reactions,
    int? replyCount,
    DateTime? lastReplyAt,
    ReplyTo? replyTo,
    List<FileRef>? attachments,
  }) {
    return Message(
      id: id,
      channelId: channelId,
      userId: userId,
      author: author,
      body: body ?? this.body,
      kind: kind,
      parentId: parentId,
      replyToId: replyToId,
      replyTo: replyTo ?? this.replyTo,
      inline: inline,
      createdAt: createdAt,
      editedAt: editedAt ?? this.editedAt,
      deletedAt: deletedAt ?? this.deletedAt,
      replyCount: replyCount ?? this.replyCount,
      lastReplyAt: lastReplyAt ?? this.lastReplyAt,
      pinned: pinned ?? this.pinned,
      reactions: reactions ?? this.reactions,
      attachments: attachments ?? this.attachments,
    );
  }
}

// ── Channels & DMs ─────────────────────────────────────────────

class Channel {
  final String id;
  final String workspaceId;
  final String name;
  final String? topic;
  final String? purpose;
  final String kind; // "channel" | "dm"
  final bool isPrivate;
  final String createdBy;
  final DateTime createdAt;
  final int memberCount;
  final int unreadCount;
  final DateTime? lastMessageAt;
  final User? dmUser;
  final List<User>? members;
  final bool isMember;

  Channel({
    required this.id,
    required this.workspaceId,
    required this.name,
    this.topic,
    this.purpose,
    required this.kind,
    required this.isPrivate,
    required this.createdBy,
    required this.createdAt,
    this.memberCount = 0,
    this.unreadCount = 0,
    this.lastMessageAt,
    this.dmUser,
    this.members,
    this.isMember = true,
  });

  bool get isDm => kind == 'dm';

  String get displayName => isDm ? (dmUser?.name ?? name) : name;

  factory Channel.fromJson(Map<String, dynamic> json) {
    return Channel(
      id: json['id'] as String? ?? '',
      workspaceId: json['workspace_id'] as String? ?? '',
      name: json['name'] as String? ?? '',
      topic: json['topic'] as String?,
      purpose: json['purpose'] as String?,
      kind: json['kind'] as String? ?? 'channel',
      isPrivate: json['is_private'] as bool? ?? false,
      createdBy: json['created_by'] as String? ?? '',
      createdAt: DateTime.tryParse(json['created_at'] as String? ?? '') ?? DateTime.now(),
      memberCount: json['member_count'] as int? ?? 0,
      unreadCount: json['unread_count'] as int? ?? 0,
      lastMessageAt: json['last_message_at'] != null ? DateTime.tryParse(json['last_message_at'] as String) : null,
      dmUser: json['dm_user'] != null ? User.fromJson(json['dm_user'] as Map<String, dynamic>) : null,
      members: (json['members'] as List<dynamic>?)?.map((e) => User.fromJson(e as Map<String, dynamic>)).toList(),
      isMember: json['is_member'] as bool? ?? true,
    );
  }

  Channel copyWith({
    int? unreadCount,
    DateTime? lastMessageAt,
    String? topic,
    String? name,
    User? dmUser,
  }) {
    return Channel(
      id: id,
      workspaceId: workspaceId,
      name: name ?? this.name,
      topic: topic ?? this.topic,
      purpose: purpose,
      kind: kind,
      isPrivate: isPrivate,
      createdBy: createdBy,
      createdAt: createdAt,
      memberCount: memberCount,
      unreadCount: unreadCount ?? this.unreadCount,
      lastMessageAt: lastMessageAt ?? this.lastMessageAt,
      dmUser: dmUser ?? this.dmUser,
      members: members,
      isMember: isMember,
    );
  }
}

// ── Schedule ───────────────────────────────────────────────────

enum EventResponse {
  accepted,
  declined,
  tentative,
  pending;

  static EventResponse fromString(String? val) {
    switch (val) {
      case 'accepted':
        return EventResponse.accepted;
      case 'declined':
        return EventResponse.declined;
      case 'tentative':
        return EventResponse.tentative;
      default:
        return EventResponse.pending;
    }
  }

  String get label {
    switch (this) {
      case EventResponse.accepted:
        return '참석';
      case EventResponse.tentative:
        return '미정';
      case EventResponse.declined:
        return '불참';
      case EventResponse.pending:
        return '대기';
    }
  }
}

class ScheduleAttendee {
  final User user;
  final EventResponse response;

  ScheduleAttendee({required this.user, required this.response});

  factory ScheduleAttendee.fromJson(Map<String, dynamic> json) {
    return ScheduleAttendee(
      user: User.fromJson(json['user'] as Map<String, dynamic>? ?? {}),
      response: EventResponse.fromString(json['response'] as String?),
    );
  }
}

class ScheduleEvent {
  final String id;
  final String workspaceId;
  final String title;
  final String description;
  final String location;
  final DateTime startsAt;
  final DateTime endsAt;
  final bool allDay;
  final bool isPrivate;
  final String createdBy;
  final String? channelId;
  final DateTime createdAt;
  final DateTime updatedAt;
  final List<ScheduleAttendee> attendees;
  final EventResponse? myResponse;

  ScheduleEvent({
    required this.id,
    required this.workspaceId,
    required this.title,
    this.description = '',
    this.location = '',
    required this.startsAt,
    required this.endsAt,
    this.allDay = false,
    this.isPrivate = false,
    required this.createdBy,
    this.channelId,
    required this.createdAt,
    required this.updatedAt,
    this.attendees = const [],
    this.myResponse,
  });

  factory ScheduleEvent.fromJson(Map<String, dynamic> json) {
    return ScheduleEvent(
      id: json['id'] as String? ?? '',
      workspaceId: json['workspace_id'] as String? ?? '',
      title: json['title'] as String? ?? '',
      description: json['description'] as String? ?? '',
      location: json['location'] as String? ?? '',
      startsAt: DateTime.tryParse(json['starts_at'] as String? ?? '') ?? DateTime.now(),
      endsAt: DateTime.tryParse(json['ends_at'] as String? ?? '') ?? DateTime.now(),
      allDay: json['all_day'] as bool? ?? false,
      isPrivate: json['is_private'] as bool? ?? false,
      createdBy: json['created_by'] as String? ?? '',
      channelId: json['channel_id'] as String?,
      createdAt: DateTime.tryParse(json['created_at'] as String? ?? '') ?? DateTime.now(),
      updatedAt: DateTime.tryParse(json['updated_at'] as String? ?? '') ?? DateTime.now(),
      attendees: (json['attendees'] as List<dynamic>?)
              ?.map((e) => ScheduleAttendee.fromJson(e as Map<String, dynamic>))
              .toList() ??
          [],
      myResponse: json['my_response'] != null ? EventResponse.fromString(json['my_response'] as String) : null,
    );
  }
}

// ── Projects, Tasks, Milestones ────────────────────────────────

enum TaskStatus {
  request,
  todo,
  inProgress,
  done;

  static TaskStatus fromString(String? val) {
    switch (val) {
      case 'request':
        return TaskStatus.request;
      case 'todo':
        return TaskStatus.todo;
      case 'in-progress':
      case 'in_progress':
        return TaskStatus.inProgress;
      case 'done':
        return TaskStatus.done;
      default:
        return TaskStatus.todo;
    }
  }

  String get apiValue {
    switch (this) {
      case TaskStatus.request:
        return 'request';
      case TaskStatus.todo:
        return 'todo';
      case TaskStatus.inProgress:
        return 'in-progress';
      case TaskStatus.done:
        return 'done';
    }
  }

  String get label {
    switch (this) {
      case TaskStatus.request:
        return '요청';
      case TaskStatus.todo:
        return '할 일';
      case TaskStatus.inProgress:
        return '진행 중';
      case TaskStatus.done:
        return '완료';
    }
  }
}

class Project {
  final String id;
  final String workspaceId;
  final String name;
  final String description;
  final String purpose;
  final String deliverables;
  final String? channelId;
  final String createdBy;
  final bool isArchived;
  final DateTime createdAt;
  final DateTime updatedAt;
  final List<User> members;
  final bool isMember;
  final int openTasks;
  final int totalTasks;
  final int doneTasks;

  Project({
    required this.id,
    required this.workspaceId,
    required this.name,
    this.description = '',
    this.purpose = '',
    this.deliverables = '',
    this.channelId,
    required this.createdBy,
    this.isArchived = false,
    required this.createdAt,
    required this.updatedAt,
    this.members = const [],
    this.isMember = false,
    this.openTasks = 0,
    this.totalTasks = 0,
    this.doneTasks = 0,
  });

  factory Project.fromJson(Map<String, dynamic> json) {
    return Project(
      id: json['id'] as String? ?? '',
      workspaceId: json['workspace_id'] as String? ?? '',
      name: json['name'] as String? ?? '',
      description: json['description'] as String? ?? '',
      purpose: json['purpose'] as String? ?? '',
      deliverables: json['deliverables'] as String? ?? '',
      channelId: json['channel_id'] as String?,
      createdBy: json['created_by'] as String? ?? '',
      isArchived: json['is_archived'] as bool? ?? false,
      createdAt: DateTime.tryParse(json['created_at'] as String? ?? '') ?? DateTime.now(),
      updatedAt: DateTime.tryParse(json['updated_at'] as String? ?? '') ?? DateTime.now(),
      members: (json['members'] as List<dynamic>?)?.map((e) => User.fromJson(e as Map<String, dynamic>)).toList() ?? [],
      isMember: json['is_member'] as bool? ?? false,
      openTasks: json['open_tasks'] as int? ?? 0,
      totalTasks: json['total_tasks'] as int? ?? 0,
      doneTasks: json['done_tasks'] as int? ?? 0,
    );
  }

  /// 일부만 바꾼 새 프로젝트. (멤버 목록을 손댈 때 쓴다)
  Project copyWith({
    String? name,
    String? description,
    String? channelId,
    bool? isArchived,
    List<User>? members,
  }) {
    return Project(
      id: id,
      workspaceId: workspaceId,
      name: name ?? this.name,
      description: description ?? this.description,
      purpose: purpose,
      deliverables: deliverables,
      channelId: channelId ?? this.channelId,
      createdBy: createdBy,
      isArchived: isArchived ?? this.isArchived,
      createdAt: createdAt,
      updatedAt: updatedAt,
      members: members ?? this.members,
      isMember: isMember,
      openTasks: openTasks,
      totalTasks: totalTasks,
      doneTasks: doneTasks,
    );
  }
}

class TaskComment {
  final String id;
  final String taskId;
  final String userId;
  final User author;
  final String body;
  final DateTime createdAt;

  TaskComment({
    required this.id,
    required this.taskId,
    required this.userId,
    required this.author,
    required this.body,
    required this.createdAt,
  });

  factory TaskComment.fromJson(Map<String, dynamic> json) {
    return TaskComment(
      id: json['id'] as String? ?? '',
      taskId: json['task_id'] as String? ?? '',
      userId: json['user_id'] as String? ?? '',
      author: User.fromJson(json['author'] as Map<String, dynamic>? ?? {}),
      body: json['body'] as String? ?? '',
      createdAt: DateTime.tryParse(json['created_at'] as String? ?? '') ?? DateTime.now(),
    );
  }
}

class Task {
  final String id;
  final String projectId;
  final String title;
  final String description;
  final TaskStatus status;
  final String? roadmapId;
  final String? roadmapName;
  final String? milestoneId;
  final String? milestoneName;
  final String? milestoneColor;
  final String? assigneeId;
  final User? assignee;
  final String createdBy;
  final DateTime? startAt;
  final DateTime? dueAt;
  final int position;
  final DateTime createdAt;
  final DateTime updatedAt;
  final List<TaskComment> comments;
  final int commentCount;

  Task({
    required this.id,
    required this.projectId,
    required this.title,
    this.description = '',
    required this.status,
    this.roadmapId,
    this.roadmapName,
    this.milestoneId,
    this.milestoneName,
    this.milestoneColor,
    this.assigneeId,
    this.assignee,
    required this.createdBy,
    this.startAt,
    this.dueAt,
    this.position = 0,
    required this.createdAt,
    required this.updatedAt,
    this.comments = const [],
    this.commentCount = 0,
  });

  factory Task.fromJson(Map<String, dynamic> json) {
    return Task(
      id: json['id'] as String? ?? '',
      projectId: json['project_id'] as String? ?? '',
      title: json['title'] as String? ?? '',
      description: json['description'] as String? ?? '',
      status: TaskStatus.fromString(json['status'] as String?),
      roadmapId: json['roadmap_id'] as String?,
      roadmapName: json['roadmap_name'] as String?,
      milestoneId: json['milestone_id'] as String?,
      milestoneName: json['milestone_name'] as String?,
      milestoneColor: json['milestone_color'] as String?,
      assigneeId: json['assignee_id'] as String?,
      assignee: json['assignee'] != null ? User.fromJson(json['assignee'] as Map<String, dynamic>) : null,
      createdBy: json['created_by'] as String? ?? '',
      startAt: json['start_at'] != null ? DateTime.tryParse(json['start_at'] as String) : null,
      dueAt: json['due_at'] != null ? DateTime.tryParse(json['due_at'] as String) : null,
      position: json['position'] as int? ?? 0,
      createdAt: DateTime.tryParse(json['created_at'] as String? ?? '') ?? DateTime.now(),
      updatedAt: DateTime.tryParse(json['updated_at'] as String? ?? '') ?? DateTime.now(),
      comments: (json['comments'] as List<dynamic>?)
              ?.map((e) => TaskComment.fromJson(e as Map<String, dynamic>))
              .toList() ??
          [],
      commentCount: json['comment_count'] as int? ?? 0,
    );
  }

  Task copyWith({
    String? title,
    String? description,
    TaskStatus? status,
    User? assignee,
    String? assigneeId,
    DateTime? dueAt,
    List<TaskComment>? comments,
    int? commentCount,
  }) {
    return Task(
      id: id,
      projectId: projectId,
      title: title ?? this.title,
      description: description ?? this.description,
      status: status ?? this.status,
      roadmapId: roadmapId,
      roadmapName: roadmapName,
      milestoneId: milestoneId,
      milestoneName: milestoneName,
      milestoneColor: milestoneColor,
      assigneeId: assigneeId ?? this.assigneeId,
      assignee: assignee ?? this.assignee,
      createdBy: createdBy,
      startAt: startAt,
      dueAt: dueAt ?? this.dueAt,
      position: position,
      createdAt: createdAt,
      updatedAt: updatedAt,
      comments: comments ?? this.comments,
      commentCount: commentCount ?? this.commentCount,
    );
  }
}

class Roadmap {
  final String id;
  final String projectId;
  final String name;
  final int position;
  final int taskCount;

  Roadmap({required this.id, required this.projectId, required this.name, this.position = 0, this.taskCount = 0});

  factory Roadmap.fromJson(Map<String, dynamic> json) {
    return Roadmap(
      id: json['id'] as String? ?? '',
      projectId: json['project_id'] as String? ?? '',
      name: json['name'] as String? ?? '',
      position: json['position'] as int? ?? 0,
      taskCount: json['task_count'] as int? ?? 0,
    );
  }
}

class Milestone {
  final String id;
  final String projectId;
  final String title;
  final DateTime startAt;
  final DateTime endAt;
  final String color;
  final double progress;
  final String description;
  final int taskCount;
  final int doneCount;

  Milestone({
    required this.id,
    required this.projectId,
    required this.title,
    required this.startAt,
    required this.endAt,
    required this.color,
    this.progress = 0,
    this.description = '',
    this.taskCount = 0,
    this.doneCount = 0,
  });

  factory Milestone.fromJson(Map<String, dynamic> json) {
    return Milestone(
      id: json['id'] as String? ?? '',
      projectId: json['project_id'] as String? ?? '',
      title: json['title'] as String? ?? '',
      startAt: DateTime.tryParse(json['start_at'] as String? ?? '') ?? DateTime.now(),
      endAt: DateTime.tryParse(json['end_at'] as String? ?? '') ?? DateTime.now(),
      color: json['color'] as String? ?? '#1C785C',
      progress: (json['progress'] as num?)?.toDouble() ?? 0.0,
      description: json['description'] as String? ?? '',
      taskCount: json['task_count'] as int? ?? 0,
      doneCount: json['done_count'] as int? ?? 0,
    );
  }
}

// ── Organization ───────────────────────────────────────────────

class OrgUnit {
  final String id;
  final String workspaceId;
  final String? parentId;
  final String name;
  final String kind;
  final String description;
  final int depth;
  final int memberCount;
  final int childCount;
  final List<User> members;
  final List<User> managers;

  OrgUnit({
    required this.id,
    required this.workspaceId,
    this.parentId,
    required this.name,
    this.kind = '부서',
    this.description = '',
    this.depth = 0,
    this.memberCount = 0,
    this.childCount = 0,
    this.members = const [],
    this.managers = const [],
  });

  factory OrgUnit.fromJson(Map<String, dynamic> json) {
    return OrgUnit(
      id: json['id'] as String? ?? '',
      workspaceId: json['workspace_id'] as String? ?? '',
      parentId: json['parent_id'] as String?,
      name: json['name'] as String? ?? '',
      kind: json['kind'] as String? ?? '부서',
      description: json['description'] as String? ?? '',
      depth: json['depth'] as int? ?? 0,
      memberCount: json['member_count'] as int? ?? 0,
      childCount: json['child_count'] as int? ?? 0,
      members: (json['members'] as List<dynamic>?)?.map((e) => User.fromJson(e as Map<String, dynamic>)).toList() ?? [],
      managers: (json['managers'] as List<dynamic>?)?.map((e) => User.fromJson(e as Map<String, dynamic>)).toList() ?? [],
    );
  }
}

class OrgOverview {
  final List<OrgUnit> units;
  final List<Member> admins;
  final Role myRole;

  OrgOverview({required this.units, required this.admins, required this.myRole});

  factory OrgOverview.fromJson(Map<String, dynamic> json) {
    return OrgOverview(
      units: (json['units'] as List<dynamic>?)?.map((e) => OrgUnit.fromJson(e as Map<String, dynamic>)).toList() ?? [],
      admins: (json['admins'] as List<dynamic>?)?.map((e) => Member.fromJson(e as Map<String, dynamic>)).toList() ?? [],
      myRole: Role.fromString(json['my_role'] as String?),
    );
  }
}

// ── Search & Bootstrap ────────────────────────────────────────

class SearchResult {
  final Message message;
  final Channel channel;

  SearchResult({required this.message, required this.channel});

  factory SearchResult.fromJson(Map<String, dynamic> json) {
    return SearchResult(
      message: Message.fromJson(json['message'] as Map<String, dynamic>),
      channel: Channel.fromJson(json['channel'] as Map<String, dynamic>),
    );
  }
}

class Bootstrap {
  final Workspace workspace;
  final List<Channel> channels;
  final List<Channel> dms;
  final List<Member> members;
  final User me;

  Bootstrap({
    required this.workspace,
    required this.channels,
    required this.dms,
    required this.members,
    required this.me,
  });

  factory Bootstrap.fromJson(Map<String, dynamic> json) {
    return Bootstrap(
      workspace: Workspace.fromJson(json['workspace'] as Map<String, dynamic>),
      channels: (json['channels'] as List<dynamic>?)
              ?.map((e) => Channel.fromJson(e as Map<String, dynamic>))
              .toList() ??
          [],
      dms: (json['dms'] as List<dynamic>?)?.map((e) => Channel.fromJson(e as Map<String, dynamic>)).toList() ?? [],
      members: (json['members'] as List<dynamic>?)?.map((e) => Member.fromJson(e as Map<String, dynamic>)).toList() ?? [],
      me: User.fromJson(json['me'] as Map<String, dynamic>),
    );
  }
}

class Session {
  final String accessToken;
  final String refreshToken;
  final User user;
  final Workspace workspace;

  Session({
    required this.accessToken,
    required this.refreshToken,
    required this.user,
    required this.workspace,
  });

  factory Session.fromJson(Map<String, dynamic> json) {
    return Session(
      accessToken: json['access_token'] as String? ?? '',
      refreshToken: json['refresh_token'] as String? ?? '',
      user: User.fromJson(json['user'] as Map<String, dynamic>),
      workspace: Workspace.fromJson(json['workspace'] as Map<String, dynamic>),
    );
  }
}

// ── Invite (초대장) ───────────────────────────────────────────

/// 팀에 초대한 한 사람.
/// `token` 은 초대장이 담긴 주소(/?invite=token) 를 만드는 재료다.
class Invite {
  final String id;
  final String workspaceId;
  final String email;
  final String role;
  final String token;
  final String createdBy;
  final DateTime? createdAt;
  final DateTime? expiresAt;

  Invite({
    required this.id,
    required this.workspaceId,
    required this.email,
    required this.role,
    required this.token,
    required this.createdBy,
    this.createdAt,
    this.expiresAt,
  });

  factory Invite.fromJson(Map<String, dynamic> json) {
    return Invite(
      id: json['id'] as String? ?? '',
      workspaceId: json['workspace_id'] as String? ?? '',
      email: json['email'] as String? ?? '',
      role: json['role'] as String? ?? 'member',
      token: json['token'] as String? ?? '',
      createdBy: json['created_by'] as String? ?? '',
      createdAt: json['created_at'] != null
          ? DateTime.tryParse(json['created_at'] as String)
          : null,
      expiresAt: json['expires_at'] != null
          ? DateTime.tryParse(json['expires_at'] as String)
          : null,
    );
  }
}
