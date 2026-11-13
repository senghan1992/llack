part of 'app_state.dart';

/// 일정 / 프로젝트 / 조직도 / 검색 부분.
abstract class _AppStateWorkspace extends _AppStateMessages {
  _AppStateWorkspace({super.api, super.ws});
  // ── Schedule ─────────────────────────────────────────────────

  Future<void> loadEvents() async {
    if (_activeWorkspace == null) return;
    _isLoadingEvents = true;
    _notify();
    try {
      _events = await api.getEvents(_activeWorkspace!.id);
      _eventsError = null;
      // 불러오기에 성공했다. (빈 목록이어도 "불러온 것" 이다)
      _hasLoadedEvents = true;
    } catch (e) {
      debugPrint('[getEvents error] $e');
      _eventsError = '일정을 불러오지 못했습니다. 다시 시도해주세요.';
    } finally {
      _isLoadingEvents = false;
      _notify();
    }
  }

  void setSelectedDate(DateTime date) {
    _selectedDate = date;
    _notify();
  }

  void toggleOnlyMyEvents() {
    _onlyMyEvents = !_onlyMyEvents;
    _notify();
  }

  Future<ScheduleEvent> createEvent({
    required String title,
    String? description,
    String? location,
    required DateTime startsAt,
    required DateTime endsAt,
    bool allDay = false,
    bool isPrivate = false,
    String? channelId,
    List<String>? attendeeIds,
  }) async {
    if (_activeWorkspace == null) throw Exception('활성 워크스페이스가 없습니다');
    final ev = await api.createEvent(
      workspaceId: _activeWorkspace!.id,
      title: title,
      description: description,
      location: location,
      startsAt: startsAt,
      endsAt: endsAt,
      allDay: allDay,
      isPrivate: isPrivate,
      channelId: channelId,
      attendeeIds: attendeeIds,
    );
    // WS 로 이미 들어왔을 수 있다. id 로 upsert 해서 항상 1개만 남긴다.
    _events = upsertById(_events, ev, (e) => e.id);
    _notify();
    return ev;
  }

  /// RSVP 를 바꾼다. 실패하면 false 를 돌려준다. (호출부가 스낵바를 띄운다)
  Future<bool> rsvpEvent(String eventId, EventResponse response) async {
    try {
      final updated = await api.rsvpEvent(eventId, response);
      final idx = _events.indexWhere((e) => e.id == eventId);
      if (idx != -1) {
        _events[idx] = updated;
        _notify();
      }
      return true;
    } catch (e) {
      debugPrint('[rsvpEvent error] $e');
      return false;
    }
  }

  /// 일정을 고친다. 실패하면 false 를 돌려주고 목록은 그대로 둔다.
  /// (§9-1 규칙: 백엔드가 PATCH 직후 WS 로 같은 이벤트를 먼저 보내므로
  ///  목록 갱신은 id 기준 upsert 로 한다.)
  Future<bool> updateEvent({
    required String eventId,
    String? title,
    String? description,
    String? location,
    DateTime? startsAt,
    DateTime? endsAt,
    bool? allDay,
    bool? isPrivate,
    String? channelId,
    List<String>? attendeeIds,
  }) async {
    try {
      final updated = await api.updateEvent(
        eventId: eventId,
        title: title,
        description: description,
        location: location,
        startsAt: startsAt,
        endsAt: endsAt,
        allDay: allDay,
        isPrivate: isPrivate,
        channelId: channelId,
        attendeeIds: attendeeIds,
      );
      // WS 로 이미 들어왔을 수 있다. id 로 upsert 해서 항상 1개만 남긴다.
      _events = upsertById(_events, updated, (e) => e.id);
      _notify();
      return true;
    } catch (e) {
      debugPrint('[updateEvent error] $e');
      return false;
    }
  }

  /// 일정을 지운다. 실패하면 false 를 돌려주고 목록에서는 지우지 않는다.
  Future<bool> deleteEvent(String eventId) async {
    try {
      await api.deleteEvent(eventId);
      _events.removeWhere((e) => e.id == eventId);
      _notify();
      return true;
    } catch (e) {
      debugPrint('[deleteEvent error] $e');
      return false;
    }
  }

  // ── Projects & Tasks ─────────────────────────────────────────

  Future<void> loadProjects() async {
    if (_activeWorkspace == null) return;
    try {
      _projects = await api.getProjects(_activeWorkspace!.id);
      _projectsError = null;
      // 불러오기에 성공했다. (빈 목록이어도 "불러온 것" 이다)
      _hasLoadedProjects = true;

      // 새로 불러온 목록은 이전과 다른 객체 인스턴스다.
      // 선택 중인 프로젝트를 옛 객체를 그대로 들고 있으면
      // DropdownButton 이 "선택값이 목록에 없다" 는 assertion 으로 죽는다.
      // 그래서 id 로 다시 찾아서 선택 상태를 목록과 맞춰준다.
      final prevId = _activeProject?.id;
      if (prevId == null) {
        // 선택된 프로젝트가 없다 → 첫 번째 프로젝트로 옮긴다.
        if (_projects.isNotEmpty) {
          await selectProject(_projects.first);
        }
      } else {
        final idx = _projects.indexWhere((p) => p.id == prevId);
        if (idx == -1) {
          // 선택했던 프로젝트가 목록에서 사라졌다. 선택을 비우고 첫 번째로 옮긴다.
          _activeProject = null;
          _selectedRoadmapId = null;
          if (_projects.isNotEmpty) {
            await selectProject(_projects.first);
          }
        } else {
          _activeProject = _projects[idx];
          // 서버 주소가 바뀌었을 수 있으므로 선택된 프로젝트의 하위 데이터도 다시 불러온다.
          await Future.wait([
            loadTasks(_projects[idx].id),
            loadRoadmaps(_projects[idx].id),
            loadMilestones(_projects[idx].id),
          ]);
        }
      }
      _notify();
    } catch (e) {
      debugPrint('[getProjects error] $e');
      _projectsError = '프로젝트를 불러오지 못했습니다. 다시 시도해주세요.';
    }
  }

  /// 프로젝트를 선택한다.
  /// 선택 상태는 항상 "목록에 있는 객체" 로 유지한다.
  /// (목록 밖 인스턴스를 들고 있으면 드롭다운이 "선택값이 목록에 없다" 는
  ///  assertion 으로 죽을 수 있다)
  Future<void> selectProject(Project project) async {
    final idx = _projects.indexWhere((p) => p.id == project.id);
    if (idx != -1) {
      _activeProject = _projects[idx];
    } else {
      // 검색 결과 등으로 목록에 없던 프로젝트를 골랐으면 목록에 넣는다.
      _projects.add(project);
      _activeProject = project;
    }
    _selectedRoadmapId = null;
    _notify();
    await Future.wait([
      loadTasks(project.id),
      loadRoadmaps(project.id),
      loadMilestones(project.id),
    ]);
  }

  Future<void> loadTasks(String projectId) async {
    try {
      final tasks = await api.getProjectTasks(projectId);
      _projectTasks[projectId] = tasks;
      _notify();
    } catch (e) {
      debugPrint('[loadTasks error] $e');
    }
  }

  Future<void> loadRoadmaps(String projectId) async {
    try {
      final roadmaps = await api.getRoadmaps(projectId);
      _projectRoadmaps[projectId] = roadmaps;
      _notify();
    } catch (e) {
      debugPrint('[loadRoadmaps error] $e');
    }
  }

  Future<void> loadMilestones(String projectId) async {
    try {
      final milestones = await api.getMilestones(projectId);
      _projectMilestones[projectId] = milestones;
      _notify();
    } catch (e) {
      debugPrint('[loadMilestones error] $e');
    }
  }

  void filterRoadmap(String? roadmapId) {
    _selectedRoadmapId = roadmapId;
    _notify();
  }

  Future<Project> createProject({
    required String name,
    String? description,
    String? channelId,
    List<String>? memberIds,
  }) async {
    if (_activeWorkspace == null) throw Exception('활성 워크스페이스가 없습니다');
    final proj = await api.createProject(
      workspaceId: _activeWorkspace!.id,
      name: name,
      description: description,
      channelId: channelId,
      memberIds: memberIds,
    );
    // 같은 규칙으로 넣는다 (나중에 WS 로 같은 항목이 와도 1개).
    _projects = upsertById(_projects, proj, (p) => p.id);
    await selectProject(proj);
    return proj;
  }

  Future<Task> createTask({
    required String title,
    String? description,
    TaskStatus status = TaskStatus.todo,
    String? assigneeId,
    DateTime? dueAt,
    String? roadmapId,
    String? milestoneId,
  }) async {
    if (_activeProject == null) throw Exception('선택된 프로젝트가 없습니다');
    final task = await api.createTask(
      projectId: _activeProject!.id,
      title: title,
      description: description,
      status: status,
      assigneeId: assigneeId,
      dueAt: dueAt,
      roadmapId: roadmapId,
      milestoneId: milestoneId,
    );
    final list = _projectTasks[_activeProject!.id] ?? [];
    // WS 로 이미 들어왔을 수 있다. id 로 upsert 해서 항상 1개만 남긴다.
    _projectTasks[_activeProject!.id] = upsertById(list, task, (t) => t.id);
    _notify();
    return task;
  }

  /// 할 일 상태를 바꾼다. 실패하면 false 를 돌려준다. (호출부가 스낵바를 띄운다)
  Future<bool> updateTaskStatus(Task task, TaskStatus newStatus) async {
    try {
      final updated = await api.updateTask(task.id, status: newStatus);
      final pid = task.projectId;
      final list = _projectTasks[pid] ?? [];
      final idx = list.indexWhere((t) => t.id == task.id);
      if (idx != -1) {
        list[idx] = updated;
        _projectTasks[pid] = List.from(list);
        _notify();
      }
      return true;
    } catch (e) {
      debugPrint('[updateTaskStatus error] $e');
      return false;
    }
  }

  /// 할 일의 제목/설명/담당자/마감일/마일스톤을 고친다. 실패하면 false 를 돌려준다.
  /// null 인 인자는 "변경 안 함" 이다.
  /// (§9-1 규칙: 백엔드가 PATCH 직후 WS `task.updated` 를 먼저 보내므로,
  ///  목록 갱신은 id 기준 upsert 로 해서 순서와 무관하게 항상 1개다.)
  Future<bool> updateTask({
    required String taskId,
    String? title,
    String? description,
    String? assigneeId,
    DateTime? dueAt,
    String? roadmapId,
    String? milestoneId,
    int? position,
  }) async {
    try {
      final updated = await api.updateTask(
        taskId,
        title: title,
        description: description,
        assigneeId: assigneeId,
        dueAt: dueAt,
        roadmapId: roadmapId,
        milestoneId: milestoneId,
        position: position,
      );
      if (_activeProject != null) {
        final list = _projectTasks[_activeProject!.id] ?? [];
        _projectTasks[_activeProject!.id] = upsertById(list, updated, (t) => t.id);
        _notify();
      }
      return true;
    } catch (e) {
      debugPrint('[updateTask error] $e');
      return false;
    }
  }

  /// 의견(댓글)을 지운다. 실패하면 false 를 돌려준다.
  Future<bool> deleteTaskComment(String taskId, String commentId) async {
    try {
      await api.deleteTaskComment(commentId);
      if (_activeProject != null) {
        final list = _projectTasks[_activeProject!.id] ?? [];
        final idx = list.indexWhere((t) => t.id == taskId);
        if (idx != -1) {
          final t = list[idx];
          final comments = t.comments.where((c) => c.id != commentId).toList();
          list[idx] = t.copyWith(comments: comments);
          _projectTasks[_activeProject!.id] = List.from(list);
          _notify();
        }
      }
      return true;
    } catch (e) {
      debugPrint('[deleteTaskComment error] $e');
      return false;
    }
  }

  // ── Project 관리 ─────────────────────────────────────────────

  /// 프로젝트를 고친다. (이름 · 설명 · 연결 채널 · 멤버 · 보관)
  Future<bool> updateProject({
    required String projectId,
    String? name,
    String? description,
    String? channelId,
    List<String>? memberIds,
    bool? isArchived,
  }) async {
    try {
      final updated = await api.updateProject(
        projectId,
        name: name,
        description: description,
        channelId: channelId,
        memberIds: memberIds,
        isArchived: isArchived,
      );
      _projects = upsertById(_projects, updated, (p) => p.id);
      if (_activeProject?.id == projectId) {
        _activeProject = updated;
      }
      _notify();
      return true;
    } catch (e) {
      debugPrint('[updateProject error] $e');
      return false;
    }
  }

  /// 프로젝트를 지운다.
  Future<bool> deleteProject(String projectId) async {
    try {
      await api.deleteProject(projectId);
      _projects = _projects.where((p) => p.id != projectId).toList();
      _projectTasks.remove(projectId);
      _projectRoadmaps.remove(projectId);
      _projectMilestones.remove(projectId);
      if (_activeProject?.id == projectId) {
        _activeProject = null;
      }
      _notify();
      return true;
    } catch (e) {
      debugPrint('[deleteProject error] $e');
      return false;
    }
  }

  /// 프로젝트에 사람을 넣는다.
  Future<bool> addProjectMember(String projectId, String userId) async {
    try {
      await api.addProjectMember(projectId, userId);
      final project = _projects.firstWhere((p) => p.id == projectId);
      final user = _members.firstWhere((m) => m.user.id == userId).user;
      final updated = project.copyWith(members: [...project.members, user]);
      _projects = upsertById(_projects, updated, (p) => p.id);
      if (_activeProject?.id == projectId) _activeProject = updated;
      _notify();
      return true;
    } catch (e) {
      debugPrint('[addProjectMember error] $e');
      return false;
    }
  }

  /// 프로젝트에서 사람을 뺀다.
  Future<bool> removeProjectMember(String projectId, String userId) async {
    try {
      await api.removeProjectMember(projectId, userId);
      final project = _projects.firstWhere((p) => p.id == projectId);
      final updated = project.copyWith(
        members: project.members.where((u) => u.id != userId).toList(),
      );
      _projects = upsertById(_projects, updated, (p) => p.id);
      if (_activeProject?.id == projectId) _activeProject = updated;
      _notify();
      return true;
    } catch (e) {
      debugPrint('[removeProjectMember error] $e');
      return false;
    }
  }

  // ── Milestone & Roadmap ──────────────────────────────────────

  /// 마일스톤을 만든다.
  Future<Milestone> createMilestone({
    required String title,
    required DateTime startAt,
    required DateTime endAt,
    String description = '',
    String color = '#4f6cff',
    int progress = 0,
    List<String>? taskIds,
  }) async {
    final pid = _activeProject?.id;
    if (pid == null) throw Exception('선택된 프로젝트가 없습니다');
    final milestone = await api.createMilestone(
      pid,
      title: title,
      startAt: startAt,
      endAt: endAt,
      description: description,
      color: color,
      progress: progress,
      taskIds: taskIds,
    );
    _projectMilestones[pid] = upsertById(
      _projectMilestones[pid] ?? const [],
      milestone,
      (m) => m.id,
    );
    _notify();
    return milestone;
  }

  /// 마일스톤을 고친다.
  Future<bool> updateMilestone({
    required String milestoneId,
    String? title,
    DateTime? startAt,
    DateTime? endAt,
    String? description,
    String? color,
    int? progress,
    List<String>? taskIds,
  }) async {
    try {
      final updated = await api.updateMilestone(
        milestoneId,
        title: title,
        startAt: startAt,
        endAt: endAt,
        description: description,
        color: color,
        progress: progress,
        taskIds: taskIds,
      );
      for (final pid in _projectMilestones.keys.toList()) {
        final list = _projectMilestones[pid] ?? [];
        if (list.any((m) => m.id == milestoneId)) {
          _projectMilestones[pid] = upsertById(list, updated, (m) => m.id);
        }
      }
      _notify();
      return true;
    } catch (e) {
      debugPrint('[updateMilestone error] $e');
      return false;
    }
  }

  /// 마일스톤을 지운다.
  Future<bool> deleteMilestone(String milestoneId) async {
    try {
      await api.deleteMilestone(milestoneId);
      for (final pid in _projectMilestones.keys.toList()) {
        _projectMilestones[pid] =
            (_projectMilestones[pid] ?? []).where((m) => m.id != milestoneId).toList();
      }
      _notify();
      return true;
    } catch (e) {
      debugPrint('[deleteMilestone error] $e');
      return false;
    }
  }

  /// 로드맵을 지운다.
  Future<bool> deleteRoadmap(String roadmapId) async {
    try {
      await api.deleteRoadmap(roadmapId);
      for (final pid in _projectRoadmaps.keys.toList()) {
        _projectRoadmaps[pid] =
            (_projectRoadmaps[pid] ?? []).where((r) => r.id != roadmapId).toList();
      }
      if (_selectedRoadmapId == roadmapId) _selectedRoadmapId = null;
      _notify();
      return true;
    } catch (e) {
      debugPrint('[deleteRoadmap error] $e');
      return false;
    }
  }

  Future<void> addTaskComment(String taskId, String body) async {
    final comment = await api.addTaskComment(taskId, body);
    if (_activeProject != null) {
      final list = _projectTasks[_activeProject!.id] ?? [];
      final idx = list.indexWhere((t) => t.id == taskId);
      if (idx != -1) {
        final t = list[idx];
        // WS 로 이미 들어온 코멘트와 같은 id 면 1개로 합친다 (§9-22).
        final updatedComments = upsertById(t.comments, comment, (c) => c.id);
        list[idx] = t.copyWith(comments: updatedComments);
        _projectTasks[_activeProject!.id] = List.from(list);
        _notify();
      }
    }
  }

  /// 할 일을 지운다. 실패하면 false 를 돌려주고 목록에서는 지우지 않는다.
  Future<bool> deleteTask(String taskId) async {
    try {
      await api.deleteTask(taskId);
      if (_activeProject != null) {
        final list = _projectTasks[_activeProject!.id] ?? [];
        _projectTasks[_activeProject!.id] = list.where((t) => t.id != taskId).toList();
        _notify();
      }
      return true;
    } catch (e) {
      debugPrint('[deleteTask error] $e');
      return false;
    }
  }

  // ── Organization ─────────────────────────────────────────────

  Future<void> loadOrg() async {
    if (_activeWorkspace == null) return;
    _isLoadingOrg = true;
    _notify();
    try {
      _orgOverview = await api.getOrgOverview(_activeWorkspace!.id);
      _orgError = null;
      // 불러오기에 성공했다. (빈 목록이어도 "불러온 것" 이다)
      _hasLoadedOrg = true;
    } catch (e) {
      debugPrint('[loadOrg error] $e');
      _orgError = '조직도를 불러오지 못했습니다. 다시 시도해주세요.';
    } finally {
      _isLoadingOrg = false;
      _notify();
    }
  }

  Future<OrgUnit> createOrgUnit({
    required String name,
    String? parentId,
    String kind = '부서',
    String description = '',
  }) async {
    if (_activeWorkspace == null) throw Exception('활성 워크스페이스가 없습니다');
    final unit = await api.createOrgUnit(
      workspaceId: _activeWorkspace!.id,
      name: name,
      parentId: parentId,
      kind: kind,
      description: description,
    );
    await loadOrg();
    return unit;
  }

  /// 조직 단위를 고친다. (이름 · 종류 · 설명 · 상위 조직)
  Future<bool> updateOrgUnit({
    required String unitId,
    String? name,
    String? parentId,
    String? kind,
    String? description,
  }) async {
    try {
      await api.updateOrgUnit(
        unitId,
        name: name,
        parentId: parentId,
        kind: kind,
        description: description,
      );
      await loadOrg();
      return true;
    } catch (e) {
      debugPrint('[updateOrgUnit error] $e');
      return false;
    }
  }

  /// 조직 단위를 지운다.
  Future<bool> deleteOrgUnit(String unitId) async {
    try {
      await api.deleteOrgUnit(unitId);
      await loadOrg();
      return true;
    } catch (e) {
      debugPrint('[deleteOrgUnit error] $e');
      return false;
    }
  }

  /// 조직에 사람을 넣는다.
  Future<bool> addOrgUnitMember(String unitId, String userId) async {
    try {
      await api.addOrgUnitMember(unitId, userId);
      await loadOrg();
      return true;
    } catch (e) {
      debugPrint('[addOrgUnitMember error] $e');
      return false;
    }
  }

  /// 조직에서 사람을 뺀다.
  Future<bool> removeOrgUnitMember(String unitId, String userId) async {
    try {
      await api.removeOrgUnitMember(unitId, userId);
      await loadOrg();
      return true;
    } catch (e) {
      debugPrint('[removeOrgUnitMember error] $e');
      return false;
    }
  }

  /// 조직 관리자로 임명한다.
  Future<bool> addOrgUnitManager(String unitId, String userId) async {
    try {
      await api.addOrgUnitManager(unitId, userId);
      await loadOrg();
      return true;
    } catch (e) {
      debugPrint('[addOrgUnitManager error] $e');
      return false;
    }
  }

  /// 조직 관리자에서 해임한다.
  Future<bool> removeOrgUnitManager(String unitId, String userId) async {
    try {
      await api.removeOrgUnitManager(unitId, userId);
      await loadOrg();
      return true;
    } catch (e) {
      debugPrint('[removeOrgUnitManager error] $e');
      return false;
    }
  }

  // ── Search ───────────────────────────────────────────────────

  Future<List<SearchResult>> search(String query) async {
    if (_activeWorkspace == null || query.trim().isEmpty) return [];
    return api.search(_activeWorkspace!.id, query.trim());
  }
}
