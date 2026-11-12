import 'package:llack_mobile/models/models.dart';
import 'package:llack_mobile/providers/app_state.dart';

/// 테스트에서 오류 상태/목록을 원하는 대로 주입하기 위한 AppState 대역.
///
/// AppState 의 오류 필드와 목록은 private 이라 getter 만 덮어써서 재현한다.
class FakeAppState extends AppState {
  FakeAppState({
    this.eventsErrorMessage,
    this.projectsErrorMessage,
    this.orgErrorMessage,
    this.projects = const [],
    this.activeProject,
  });

  final String? eventsErrorMessage;
  final String? projectsErrorMessage;
  final String? orgErrorMessage;

  @override
  final List<Project> projects;

  @override
  final Project? activeProject;

  int eventsRetryCount = 0;
  int projectsRetryCount = 0;
  int orgRetryCount = 0;

  /// 드롭다운에서 선택이 전달되었는지 확인하기 위한 기록
  Project? lastSelectedProject;

  @override
  String? get eventsError => eventsErrorMessage;

  @override
  String? get projectsError => projectsErrorMessage;

  @override
  String? get orgError => orgErrorMessage;

  @override
  Future<void> retryEvents() async {
    eventsRetryCount++;
  }

  @override
  Future<void> retryProjects() async {
    projectsRetryCount++;
  }

  @override
  Future<void> retryOrg() async {
    orgRetryCount++;
  }

  @override
  Future<void> selectProject(Project project) async {
    lastSelectedProject = project;
  }
}
