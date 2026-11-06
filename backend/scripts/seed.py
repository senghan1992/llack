"""Seed the demo workspace ``한빛`` (slug ``hanbit``).

Running the script twice is safe: it does nothing when the demo workspace
already exists.

    cd backend && .venv/bin/python scripts/seed.py
"""

from __future__ import annotations

import asyncio
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from sqlalchemy import func, select  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: E402

from app.core.db import SessionLocal, create_all  # noqa: E402
from app.core.ids import (  # noqa: E402
    ATTENDEE_PREFIX,
    CHANNEL_MEMBER_PREFIX,
    CHANNEL_PREFIX,
    EVENT_PREFIX,
    MEMBER_PREFIX,
    MESSAGE_PREFIX,
    MILESTONE_PREFIX,
    ORG_MANAGER_PREFIX,
    ORG_MEMBER_PREFIX,
    ORG_UNIT_PREFIX,
    PROJECT_MEMBER_PREFIX,
    PROJECT_PREFIX,
    REACTION_PREFIX,
    TASK_PREFIX,
    USER_PREFIX,
    WORKSPACE_PREFIX,
    new_id,
)
from app.core.security import hash_password  # noqa: E402
from app.models.channel import KIND_CHANNEL, KIND_DM, Channel, ChannelMember  # noqa: E402
from app.models.invite import Invite  # noqa: E402
from app.models.message import KIND_TEXT, Message, Reaction  # noqa: E402
from app.models.org import OrgUnit, OrgUnitManager, OrgUnitMember  # noqa: E402
from app.models.project import (  # noqa: E402
    STATUS_DONE,
    STATUS_IN_PROGRESS,
    STATUS_REQUEST,
    STATUS_TODO,
    Milestone,
    Project,
    ProjectMember,
    Task,
)
from app.models.schedule import (  # noqa: E402
    RESPONSE_ACCEPTED,
    RESPONSE_DECLINED,
    RESPONSE_TENTATIVE,
    ScheduleAttendee,
    ScheduleEvent,
)
from app.models.user import User  # noqa: E402
from app.models.workspace import (  # noqa: E402
    ROLE_MEMBER,
    ROLE_OWNER,
    Workspace,
    WorkspaceMembership,
)
from app.services import invites as invite_service  # noqa: E402
from app.services.channels import dm_key  # noqa: E402

WORKSPACE_NAME = "한빛"
WORKSPACE_SLUG = "hanbit"
DEMO_PASSWORD = "hanbit2026"

# The demo invitation: a code a developer can type in to join the workspace.
INVITED_EMAIL = "newcomer@hanbit.co.kr"

PEOPLE = [
    ("김현진", "hyunjin@hanbit.co.kr", "백엔드 엔지니어", "#126b47"),
    ("박지민", "jimin@hanbit.co.kr", "프로덕트 디자이너", "#8a4141"),
    ("이채원", "chaewon@hanbit.co.kr", "프론트엔드 엔지니어", "#295e90"),
    ("최수아", "sua@hanbit.co.kr", "기획자", "#814d0e"),
    ("정우진", "woojin@hanbit.co.kr", "데브옵스", "#644c8a"),
]

# (channel slug, author, body, minutes ago, replies)
# replies: list of (author, body, minutes ago)
MESSAGES: list[tuple[str, str, str, int, list[tuple[str, str, int]]]] = [
    # ── general ───────────────────────────────────────────────────────────
    (
        "general",
        "최수아",
        "오늘 오전 10시 주간 스탠드업이에요. 지난주 배포 건 후속 확인 부탁드려요.",
        1500,
        [],
    ),
    ("general", "정우진", "어제 배포는 문제없이 끝났습니다. 롤백 없이 정상 반영됐어요.", 1490, []),
    ("general", "김현진", "확인했습니다. 에러 로그 0건이고 DB 커넥션도 정상이에요.", 1485, []),
    (
        "general",
        "박지민",
        "디자인 시스템 v2 적용한 목업 공유합니다. 버튼 규격 바뀐 부분만 확인해 주세요.",
        1400,
        [],
    ),
    (
        "general",
        "이채원",
        "목록 페이지에 새 사이드바 반영했어요. 로컬에서 확인 부탁드려요.",
        1380,
        [],
    ),
    (
        "general",
        "최수아",
        "내일 점심은 뭐 먹을까요? 매일 김치찌개인데 이번 주는 좀 바꿔도 될 것 같아서요.",
        600,
        [],
    ),
    ("general", "정우진", "저도 김치찌개 찬성입니다. 근데 금요일엔 갈비 먹자고요.", 590, []),
    ("general", "박지민", "오 금요일은 저도 가능해요!", 585, []),
    ("general", "김현진", "회의실 3번 예약해 둘게요.", 580, []),
    ("general", "이채원", "사내 카페 신메뉴 나왔더라고요. 오늘은 거기서 먹을까 해요.", 180, []),
    ("general", "최수아", "신메뉴 뭐예요?", 175, []),
    ("general", "이채원", "라벤더 라떼요. 원두는 에티오피아 쪽이고 시럽은 안 들어요.", 174, []),
    (
        "general",
        "박지민",
        "라벤더 라떼. 사진 보냅니다.",
        170,
        [
            ("최수아", "예쁘네요. 내일 저도 사볼래요.", 169),
            ("이채원", "저는 아아 마시지만 이것도 궁금하긴 하네요.", 168),
        ],
    ),
    # ── engineering ───────────────────────────────────────────────────────
    (
        "engineering",
        "김현진",
        "어제 올라간 알림센터 조회가 슬로우로 걸리네요. "
        "인덱스 하나 추가해서 hotfix 준비하겠습니다.",
        1200,
        [
            ("이채원", "explain 돌린 결과 공유할게요.", 1178),
            ("김현진", "확인했습니다. 버퍼풀 히트가 92%까지 올라가네요.", 1176),
            ("정우진", "인덱스 적용하면 30ms 정도로 떨어질 것 같아요.", 1174),
            ("김현진", "PR 올렸습니다. #1427이요.", 1172),
        ],
    ),
    ("engineering", "이채원", "어떤 쿼리요? 메시지 목록 조회인가요?", 1195, []),
    (
        "engineering",
        "김현진",
        "추가로 요약 테스트 좀 부탁할게요. 버퍼풀 압박 상황에서도 커넥션이 안 새는지요.",
        1193,
        [],
    ),
    ("engineering", "김현진", "저녁까지 결과 공유하겠습니다.", 1191, []),
    (
        "engineering",
        "김현진",
        "네, workspace_id + created_at 조건으로 걸리는 거요. 파일럿 DB에서 2.8초까지 늘어났어요.",
        1190,
        [],
    ),
    ("engineering", "이채원", "그럼 커버링 인덱스로 처리하면 되겠네요.", 1185, []),
    (
        "engineering",
        "김현진",
        "맞아요. (workspace_id, channel_id, created_at desc)로 만들어서 PR 올릴게요.",
        1180,
        [],
    ),
    ("engineering", "정우진", "PR 올리면 바로 머지할까요?", 1175, []),
    (
        "engineering",
        "김현진",
        "staging에서 explain만 확인하고 바로 머지하겠습니다. 30분이면 될 것 같아요.",
        1170,
        [],
    ),
    (
        "engineering",
        "이채원",
        "프론트 쪽 websocket 재연결 버그 수정했어요. "
        "네트워크 전환이랑 슬립에서 깨어났을 때 소켓이 안 다시 붙는 문제였어요.",
        600,
        [
            ("김현진", "그럼 서버 heartbeat는 20초 주기로 하면 될 것 같아요.", 589),
            ("정우진", "서버 idle timeout은 60초로 두면 안전하겠네요.", 588),
            ("이채원", "좋아요. 그렇게 맞춰볼게요.", 587),
        ],
    ),
    (
        "engineering",
        "김현진",
        "재연결 타이밍이 좀 골치 아프죠. 서버에서 ping/pong 타임아웃 걸었나요?",
        590,
        [],
    ),
    (
        "engineering",
        "이채원",
        "아직요. 지금은 30초 안에 pong 안 오면 재연결하도록 했는데, "
        "서버 쪽에서도 같이 봐주면 좋겠어요.",
        585,
        [],
    ),
    ("engineering", "김현진", "좋아요. 오늘 서버 쪽 heartbeat 주도록 추가할게요.", 580, []),
    ("engineering", "최수아", "개발자들 오늘 배포 일정 어떻게 되나요?", 300, []),
    ("engineering", "김현진", "저녁 8시 배포 예정입니다. 핫픽스는 아니고 일반 배포예요.", 295, []),
    (
        "engineering",
        "정우진",
        "배포 전 DB 백업 자동화 스크립트 돌려주세요. 지난번처럼 수동으로 하다가 시간 날렸어요.",
        290,
        [],
    ),
    (
        "engineering",
        "김현진",
        "백업 스크립트 이번 주에 cron으로 붙였어요. 배포 파이프라인 첫 단계로도 넣어 둘게요.",
        285,
        [],
    ),
    ("engineering", "이채원", "좋아요. 그럼 이번 배포는 스탠드업 없이 조용히 갈까요?", 280, []),
    ("engineering", "최수아", "배포는 조용히 하고, 결과만 정리해서 올려주세요.", 275, []),
    ("engineering", "정우진", "로그stash 인덱스가 또 커졌네요. 일주일치만 롤링할까요?", 150, []),
    ("engineering", "김현진", "그렇게 하죠. 7일 롤링이면 용량 문제 해결될 것 같아요.", 145, []),
    (
        "engineering",
        "이채원",
        "빌드 시간 4분 30초에서 2분 50초로 줄었어요. 캐시 히트율 96%입니다.",
        100,
        [],
    ),
    ("engineering", "김현진", "오 진짜 빠르네요. 다음 배포 때 공유해 주세요.", 95, []),
    # ── design (private) ──────────────────────────────────────────────────
    (
        "design",
        "박지민",
        "신규 사이드바 목업 공유합니다. 접었을 때 아이콘 정렬이 어때요?",
        700,
        [],
    ),
    (
        "design",
        "이채원",
        "아이콘 정렬 좋아요. 근데 검색 아이콘은 조금 더 위로 올리는 게 어때요?",
        690,
        [],
    ),
    ("design", "박지민", "그게 낫겠네요. 갱신본 내일 오전에 드릴게요.", 685, []),
    (
        "design",
        "최수아",
        "디자인 시안 검토했어요. 색상 대비가 조금 약한 것 같은데 어때요?",
        400,
        [
            ("박지민", "대비 보강 버전 같이 올릴게요.", 394),
            ("이채원", "확인하면 바로 코드에 반영할게요.", 393),
        ],
    ),
    ("design", "박지민", "저도 그 부분이 걸렸어요. 대비를 조금 더 강하게 가볼게요.", 395, []),
    ("design", "이채원", "다크모드에서는 밝은 배경이 튀어서 대비가 확보되더라고요.", 390, []),
    ("design", "박지민", "아 그건 다크모드 얘기였군요. 라이트 모드 대비를 보강할게요.", 385, []),
    # ── release (private) ─────────────────────────────────────────────────
    ("release", "정우진", "v0.9.4 배포 체크리스트 정리했습니다. 확인 부탁드려요.", 500, []),
    (
        "release",
        "김현진",
        "DB 마이그레이션 순서 확인했어요. "
        "인덱스 추가는 online으로 가능하고, 컬럼 추가는 nullable로 처리했습니다.",
        490,
        [],
    ),
    ("release", "정우진", "그럼 롤백할 때 새 컬럼은 남겨두는 거죠?", 485, []),
    ("release", "김현진", "네. 앱 버전만 되돌리면 되게 설계했어요.", 480, []),
    ("release", "최수아", "고객사 담당자한테 배포 시간 먼저 알려드릴게요.", 300, []),
    (
        "release",
        "정우진",
        "오늘 저녁 8시, 10분 정도 걸릴 예정입니다. 끝나면 바로 공유할게요.",
        295,
        [],
    ),
    # ── random ────────────────────────────────────────────────────────────
    ("random", "박지민", "우리 팀 근처에 새로 생긴 국수집 가봤어요. 평점 괜찮더라고요.", 800, []),
    ("random", "최수아", "어디예요? 점심시간에 줄 길면 바로 접을게요.", 795, []),
    ("random", "이채원", "교대역 3번 출구 쪽이요. 반찬이 정말 많습니다.", 790, []),
    ("random", "정우진", "저도 다음 주에 가볼게요.", 785, []),
    ("random", "김현진", "저는 이번 주 토요일 마라톤 완주 목표인데 다리 때문에 망했어요.", 430, []),
    ("random", "이채원", "몇 km짜리예요?", 425, []),
    ("random", "김현진", "하프 21km. 무릎이 먼저 나갔어요.", 420, []),
    ("random", "최수아", "다음엔 걸어요. 저번에 같이 갔을 때 완주 못 한 게 아쉬웠거든요.", 415, []),
    ("random", "박지민", "짐 챙기는 게 제일 어렵더라고요.", 410, []),
    ("random", "김현진", "결국 짐을 다 패킹해서 들고 가야 했어요.", 405, []),
]

# channel slug -> (display name, topic, is_private, members)
CHANNELS = [
    ("general", "general", "팀 전체 공지와 일상적인 이야기", False, None),
    ("design", "design", "디자인 리뷰와 시안 공유", True, ["박지민", "이채원", "최수아"]),
    ("engineering", "engineering", "백엔드와 프론트엔드 개발 이야기", False, None),
    ("release", "release", "배포 일정과 릴리스 노트", True, ["정우진", "김현진", "최수아"]),
    ("random", "random", "잡담과 수다", False, None),
]

# (first user, second user, [(author, body, minutes ago)])
DIRECT_MESSAGES = [
    (
        "김현진",
        "최수아",
        [
            ("최수아", "김현진님, 알림센터 hotfix 오늘 중으로 가능할까요?", 520),
            ("김현진", "네, 지금 머지하고 있어요. 30분 안에 배포해둘게요.", 515),
            ("최수아", "고마워요. 그러면 고객사 답변은 오늘 중으로 드릴게요.", 510),
            ("김현진", "배포 완료되면 바로 알려드릴게요.", 505),
        ],
    ),
    (
        "이채원",
        "박지민",
        [
            ("이채원", "새 사이드바 목업 반영 가능한지 오늘 확인 가능할까요?", 700),
            ("박지민", "지금 열람 파일 하나 더 추가된 거 있죠? 그거까지 같이 반영할게요.", 695),
            ("이채원", "네, 맞아요. 오늘 밤에 정리해서 PR 올릴게요.", 690),
            ("박지민", "좋아요. 리뷰는 내일 오전에 할게요.", 685),
        ],
    ),
    (
        "정우진",
        "김현진",
        [
            ("정우진", "배포 스크립트에 백업 단계 추가했어요. 확인 한번만 부탁해요.", 430),
            ("김현진", "확인했어요. 실패하면 롤백되는지도 같이 넣을까요?", 425),
            ("정우진", "넹. 그게 훨씬 안전할 것 같아요.", 420),
        ],
    ),
]

# (channel slug, index of the message inside that channel, [(emoji, [user names])])
REACTIONS = [
    ("general", 1, [("🎉", ["김현진", "최수아", "박지민", "이채원"])]),
    ("general", 11, [("❤️", ["최수아", "이채원"])]),
    ("engineering", 0, [("👍", ["이채원", "정우진"]), ("👀", ["최수아"])]),
    ("engineering", 19, [("👏", ["김현진", "정우진"])]),
    ("design", 4, [("👍", ["이채원", "최수아"])]),
    ("random", 0, [("🍜", ["최수아", "정우진"])]),
]

# (channel slug, index of the message inside that channel)
PINS = [
    ("general", 1),
    ("engineering", 0),
    ("release", 0),
]

# The demo calendar.
# (title, description, location, day offset, hour, minutes, all_day, channel slug, guests)
SCHEDULE: list[tuple[str, str, str, int, int, int, bool, str | None, list[str]]] = [
    (
        "주간 스탠드업",
        "지난주 산출물과 이번 주 목표를 공유합니다.",
        "3층 회의실",
        0,
        10,
        30,
        False,
        "general",
        ["김현진", "박지민", "이채원", "최수아", "정우진"],
    ),
    (
        "디자인 리뷰",
        "목록 화면과 사이드바를 함께 봅니다.",
        "2층 디자인룸",
        1,
        14,
        60,
        False,
        "design",
        ["박지민", "이채원", "최수아"],
    ),
    (
        "장애 대응 리허설",
        "알림 지연 시나리오를 함께 확인합니다.",
        "원격",
        2,
        16,
        60,
        False,
        "engineering",
        ["김현진", "정우진", "이채원"],
    ),
    (
        "분기 계획",
        "다음 분기 목표와 일정을 정리합니다.",
        "",
        4,
        0,
        0,
        True,
        None,
        ["최수아", "김현진", "박지민", "이채원"],
    ),
    (
        "1:1 (김현진 ↔ 최수아)",
        "이번 주 진행 상황 공유",
        "",
        6,
        15,
        30,
        False,
        None,
        ["김현진", "최수아"],
    ),
]


# (name, description, channel slug, creator, people on the project)
PROJECTS: list[tuple[str, str, str | None, str, list[str]]] = [
    (
        "결제 시스템 개편",
        "구독 결제를 다시 만들고, 정산을 한곳에 모읍니다. 결과물은 결제 모듈, "
        "정산 대시보드, PG사 이관 계획서.",
        "engineering",
        "김현진",
        ["김현진", "이채원", "최수아"],
    ),
    (
        "디자인 시스템 v2",
        "버튼과 입력의 규격을 하나로 모읍니다. 결과물은 토큰 문서, 컴포넌트 "
        "라이브러리, 사용 안내서.",
        "design",
        "박지민",
        ["박지민", "이채원", "최수아"],
    ),
    (
        "사내 공통 라이브러리",
        "각 팀이 다시 쓰지 않는 공통 코드를 한곳에 둡니다. 결과물은 공통 "
        "패키지, 배포 파이프라인, 사용 안내서.",
        None,
        "최수아",
        ["최수아", "정우진"],
    ),
]

# (project index, title, description, status, assignee, days until due)
TASKS: list[tuple[int, str, str, str, str | None, int | None]] = [
    (
        0,
        "PG사 계약 조건 정리",
        "정산 주기와 수수료율을 한 장으로 정리합니다.",
        STATUS_DONE,
        "최수아",
        None,
    ),
    (
        0,
        "결제 도메인 모델 초안",
        "구독·정산·환불을 어떻게 나눌지 적습니다.",
        STATUS_IN_PROGRESS,
        "김현진",
        3,
    ),
    (
        0,
        "PG사 샌드박스 연동",
        "이니시스 테스트 가이드로 붙여 봅니다.",
        STATUS_IN_PROGRESS,
        "이채원",
        6,
    ),
    (
        0,
        "정산 대시보드 화면",
        "월별 정산이 한눈에 들어오는 화면.",
        STATUS_REQUEST,
        "최수아",
        None,
    ),
    (
        0,
        "이전 결제 데이터 이관 계획",
        "어떤 순서로, 무엇을 옮길지.",
        STATUS_TODO,
        "김현진",
        10,
    ),
    (
        1,
        "토큰 이름 재정리",
        "색·공간·글꼴을 용도에 맞게 다시 묶습니다.",
        STATUS_DONE,
        "박지민",
        None,
    ),
    (
        1,
        "버튼 규격 명세",
        "주요·보조·조용한 버튼 세 가지로 정리합니다.",
        STATUS_IN_PROGRESS,
        "박지민",
        2,
    ),
    (
        1,
        "입력 필드 컴포넌트",
        "필드·라벨·오류 메시지를 한 묶음으로.",
        STATUS_TODO,
        "이채원",
        8,
    ),
    (
        1,
        "대비 검수",
        "라이트와 다크를 눈으로 한 번 더 봅니다.",
        STATUS_REQUEST,
        "최수아",
        None,
    ),
    (
        2,
        "공통 패키지 저장소 만들기",
        "이름과 배포 방식을 정합니다.",
        STATUS_IN_PROGRESS,
        "최수아",
        4,
    ),
    (
        2,
        "배포 파이프라인 정리",
        "한 번의 명령으로 배포되게 만듭니다.",
        STATUS_TODO,
        "정우진",
        12,
    ),
    (
        2,
        "이관 대상 목록 조사",
        "어느 코드가 두 번 쓰였는지 살펴봅니다.",
        STATUS_REQUEST,
        None,
        None,
    ),
]


# The dated markers of the demo board: (title, description, start in days,
# end in days, colour, manual progress, the titles of the cards that deliver it)
MILESTONES: list[tuple[str, str, int, int, str, int, list[str]]] = [
    (
        "v1.0 출시",
        "구독 결제 모듈을 고객에게 연다.",
        0,
        60,
        "#4f6cff",
        0,
        ["결제 도메인 모델 초안", "정산 대시보드 화면", "이전 결제 데이터 이관 계획"],
    ),
    (
        "결제 연동",
        "PG사 이니시스 테스트를 끝낸다.",
        14,
        45,
        "#e0803a",
        0,
        ["PG사 샌드박스 연동", "PG사 계약 조건 정리"],
    ),
]


# (name, kind, parent unit name, people in it)
ORG_UNITS: list[tuple[str, str, str | None, list[str]]] = [
    ("프로덕트 개발부", "부서", None, ["최수아", "정우진"]),
    ("개발팀", "팀", "프로덕트 개발부", ["김현진", "이채원"]),
    ("디자인팀", "팀", "프로덕트 개발부", ["박지민"]),
]

# The person who looks after the demo department.
ORG_MANAGER = "최수아"


def _now() -> datetime:
    return datetime.now(UTC)


def _at(minutes_ago: int) -> datetime:
    return _now() - timedelta(minutes=minutes_ago)


async def _seed(session: AsyncSession) -> tuple[int, int, int] | None:
    existing = await session.scalar(select(Workspace.id).where(Workspace.slug == WORKSPACE_SLUG))
    if existing is not None:
        return None

    owner_id = None
    users: dict[str, User] = {}
    for name, email, title, color in PEOPLE:
        user = User(
            id=new_id(USER_PREFIX),
            email=email,
            password_hash=hash_password(DEMO_PASSWORD),
            name=name,
            title=title,
            avatar_color=color,
            presence="offline",
            last_seen_at=_now(),
            created_at=_now(),
        )
        session.add(user)
        users[name] = user
    await session.flush()
    owner_id = users["김현진"].id

    workspace = Workspace(
        id=new_id(WORKSPACE_PREFIX),
        name=WORKSPACE_NAME,
        slug=WORKSPACE_SLUG,
        created_at=_now(),
    )
    session.add(workspace)
    for index, (_, _, _, _) in enumerate(PEOPLE):
        session.add(
            WorkspaceMembership(
                id=new_id(MEMBER_PREFIX),
                workspace_id=workspace.id,
                user_id=users[PEOPLE[index][0]].id,
                role="owner" if index == 0 else "member",
                joined_at=_now(),
            )
        )
    await session.flush()

    channels: dict[str, Channel] = {}
    for slug, name, topic, is_private, members in CHANNELS:
        channel = Channel(
            id=new_id(CHANNEL_PREFIX),
            workspace_id=workspace.id,
            name=name,
            topic=topic,
            purpose="",
            kind=KIND_CHANNEL,
            is_private=is_private,
            created_by=owner_id,
            created_at=_now(),
        )
        session.add(channel)
        await session.flush()
        channels[slug] = channel

        roster = members if members is not None else [person[0] for person in PEOPLE]
        for person in roster:
            session.add(
                ChannelMember(
                    id=new_id(CHANNEL_MEMBER_PREFIX),
                    channel_id=channel.id,
                    user_id=users[person].id,
                    joined_at=_now(),
                )
            )
    await session.flush()

    # messages, replies and their timestamps
    created: dict[tuple[str, int], Message] = {}
    per_channel: dict[str, int] = {}
    pending_replies: list[tuple[Message, str, str, int]] = []
    for slug, author, body, minutes_ago, replies in MESSAGES:
        channel = channels[slug]
        index = per_channel.get(slug, 0)
        per_channel[slug] = index + 1

        message = Message(
            id=new_id(MESSAGE_PREFIX),
            channel_id=channel.id,
            user_id=users[author].id,
            body=body,
            kind=KIND_TEXT,
            parent_id=None,
            created_at=_at(minutes_ago),
        )
        session.add(message)
        await session.flush()
        created[(slug, index)] = message

        for reply_author, reply_body, reply_minutes in replies:
            pending_replies.append((message, reply_author, reply_body, reply_minutes))
    await session.flush()

    for parent, reply_author, reply_body, reply_minutes in pending_replies:
        session.add(
            Message(
                id=new_id(MESSAGE_PREFIX),
                channel_id=parent.channel_id,
                user_id=users[reply_author].id,
                body=reply_body,
                kind=KIND_TEXT,
                parent_id=parent.id,
                created_at=_at(reply_minutes),
            )
        )
    await session.flush()

    # thread statistics
    for message in created.values():
        replies = list(
            await session.scalars(select(Message).where(Message.parent_id == message.id))
        )
        if replies:
            message.reply_count = len(replies)
            message.last_reply_at = max(reply.created_at for reply in replies)
    await session.flush()

    for slug, index, groups in REACTIONS:
        message = created.get((slug, index))
        if message is None:
            continue
        for emoji, people in groups:
            for person in people:
                session.add(
                    Reaction(
                        id=new_id(REACTION_PREFIX),
                        message_id=message.id,
                        user_id=users[person].id,
                        emoji=emoji,
                        created_at=_at(30),
                    )
                )

    for slug, index in PINS:
        message = created.get((slug, index))
        if message is not None:
            message.pinned = True

    # direct messages
    for first, second, entries in DIRECT_MESSAGES:
        key = dm_key(workspace.id, users[first].id, users[second].id)
        channel = Channel(
            id=new_id(CHANNEL_PREFIX),
            workspace_id=workspace.id,
            name=users[second].name,
            topic="",
            purpose="",
            kind=KIND_DM,
            is_private=True,
            created_by=users[first].id,
            dm_key=key,
            created_at=_now(),
        )
        session.add(channel)
        await session.flush()
        for person in (first, second):
            session.add(
                ChannelMember(
                    id=new_id(CHANNEL_MEMBER_PREFIX),
                    channel_id=channel.id,
                    user_id=users[person].id,
                    joined_at=_now(),
                )
            )
        for author, body, minutes_ago in entries:
            session.add(
                Message(
                    id=new_id(MESSAGE_PREFIX),
                    channel_id=channel.id,
                    user_id=users[author].id,
                    body=body,
                    kind=KIND_TEXT,
                    parent_id=None,
                    created_at=_at(minutes_ago),
                )
            )

    # The calendar. The guests answer in a mix, so the roster reads like a
    # real week rather than a wall of yes.
    answers = [RESPONSE_ACCEPTED, RESPONSE_TENTATIVE, RESPONSE_DECLINED]
    for index, (
        title,
        description,
        location,
        day_offset,
        hour,
        minutes,
        all_day,
        channel_slug,
        guests,
    ) in enumerate(SCHEDULE):
        starts_at = (_now() + timedelta(days=day_offset)).replace(
            hour=hour, minute=0, second=0, microsecond=0
        )
        if starts_at <= _now():
            # Today's slot has already gone by — put it an hour ahead so the
            # demo calendar opens on something that still happens.
            starts_at = (_now() + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
        ends_at = (
            starts_at + timedelta(days=1) if all_day else starts_at + timedelta(minutes=minutes)
        )
        event = ScheduleEvent(
            id=new_id(EVENT_PREFIX),
            workspace_id=workspace.id,
            title=title,
            description=description,
            location=location,
            starts_at=starts_at,
            ends_at=ends_at,
            all_day=all_day,
            is_private=False,
            created_by=users[guests[0]].id,
            channel_id=channels[channel_slug].id if channel_slug else None,
            created_at=_now(),
            updated_at=_now(),
        )
        session.add(event)
        await session.flush()
        for guest_index, person in enumerate(guests):
            if guest_index == 0:
                response = RESPONSE_ACCEPTED
            else:
                response = answers[(index + guest_index) % len(answers)]
            session.add(
                ScheduleAttendee(
                    id=new_id(ATTENDEE_PREFIX),
                    event_id=event.id,
                    user_id=users[person].id,
                    response=response,
                    created_at=_now(),
                )
            )

    # The board of work. A project is open to the workspace, and the people
    # named on it are the ones who look after it.
    await _seed_projects(session, workspace, users, channels)
    await _seed_milestones(session, workspace)

    # The organization: the units the company is arranged in.
    await _seed_org(session, workspace, users)

    await session.commit()

    users_count = await session.scalar(select(func.count()).select_from(User))
    channels_count = await session.scalar(select(func.count()).select_from(Channel))
    messages_count = await session.scalar(select(func.count()).select_from(Message))
    return int(users_count or 0), int(channels_count or 0), int(messages_count or 0)


async def _seed_projects(
    session: AsyncSession,
    workspace: Workspace,
    users: dict[str, User],
    channels: dict[str, Channel],
) -> int:
    """Put the demo projects on a workspace — once.

    A workspace that already carries projects is left alone: the board is
    the team's own work, not the seed's.
    """
    existing = await session.scalar(
        select(func.count()).select_from(Project).where(Project.workspace_id == workspace.id)
    )
    if existing:
        return 0

    projects: list[Project] = []
    for name, description, channel_slug, creator, roster in PROJECTS:
        project = Project(
            id=new_id(PROJECT_PREFIX),
            workspace_id=workspace.id,
            name=name,
            description=description,
            channel_id=channels[channel_slug].id if channel_slug else None,
            created_by=users[creator].id,
            is_archived=False,
            created_at=_now(),
            updated_at=_now(),
        )
        session.add(project)
        await session.flush()
        projects.append(project)
        for person in roster:
            session.add(
                ProjectMember(
                    id=new_id(PROJECT_MEMBER_PREFIX),
                    project_id=project.id,
                    user_id=users[person].id,
                    created_at=_now(),
                )
            )

    positions: dict[tuple[str, str], int] = {}
    for index, title, description, status, assignee, due_in_days in TASKS:
        project = projects[index]
        key = (project.id, status)
        position = positions.get(key, 0)
        positions[key] = position + 1
        due_at = _now() + timedelta(days=due_in_days) if due_in_days is not None else None
        session.add(
            Task(
                id=new_id(TASK_PREFIX),
                project_id=project.id,
                title=title,
                description=description,
                status=status,
                assignee_id=users[assignee].id if assignee else None,
                created_by=users[PROJECTS[index][3]].id,
                start_at=None,
                due_at=due_at,
                position=position,
                created_at=_now(),
                updated_at=_now(),
            )
        )
    await session.flush()
    return len(projects)


async def _seed_milestones(session: AsyncSession, workspace: Workspace) -> int:
    """Put the demo milestones on a project — once.

    A project that already carries milestones is left alone: the markers of
    a delivery are the team's own.
    """
    project = await session.scalar(
        select(Project)
        .where(Project.workspace_id == workspace.id)
        .order_by(Project.created_at, Project.id)
    )
    if project is None:
        return 0

    existing = await session.scalar(
        select(func.count()).select_from(Milestone).where(Milestone.project_id == project.id)
    )
    if existing:
        return 0

    cards = list(
        await session.scalars(
            select(Task)
            .where(Task.project_id == project.id)
            .order_by(Task.position, Task.created_at, Task.id)
        )
    )
    by_title = {card.title: card for card in cards}

    made = 0
    for title, description, start_in, end_in, color, progress, card_titles in MILESTONES:
        milestone = Milestone(
            id=new_id(MILESTONE_PREFIX),
            project_id=project.id,
            title=title,
            start_at=_now() + timedelta(days=start_in),
            end_at=_now() + timedelta(days=end_in),
            color=color,
            progress=progress,
            description=description,
            created_by=project.created_by,
            created_at=_now(),
            updated_at=_now(),
        )
        session.add(milestone)
        await session.flush()
        for card_title in card_titles:
            card = by_title.get(card_title)
            if card is not None:
                card.milestone_id = milestone.id
        made += 1
    await session.flush()
    return made


async def _seed_org(
    session: AsyncSession,
    workspace: Workspace,
    users: dict[str, User],
) -> int:
    """Put the demo organization on a workspace — once.

    A workspace that already carries an organization is left alone: the
    shape of a company is the company's own business.
    """
    existing = await session.scalar(
        select(func.count()).select_from(OrgUnit).where(OrgUnit.workspace_id == workspace.id)
    )
    if existing:
        return 0

    units: dict[str, OrgUnit] = {}
    owner = users.get(PEOPLE[0][0])
    if owner is None:
        return 0
    for name, kind, parent_name, roster in ORG_UNITS:
        parent = units.get(parent_name) if parent_name else None
        unit = OrgUnit(
            id=new_id(ORG_UNIT_PREFIX),
            workspace_id=workspace.id,
            parent_id=parent.id if parent else None,
            name=name,
            kind=kind,
            description="",
            position=0,
            created_by=owner.id,
            created_at=_now(),
            updated_at=_now(),
        )
        session.add(unit)
        await session.flush()
        units[name] = unit
        for person in roster:
            colleague = users.get(person)
            if colleague is None:
                continue
            session.add(
                OrgUnitMember(
                    id=new_id(ORG_MEMBER_PREFIX),
                    org_unit_id=unit.id,
                    user_id=colleague.id,
                    joined_at=_now(),
                )
            )
    await session.flush()

    head = units.get(ORG_UNITS[0][0])
    manager = users.get(ORG_MANAGER)
    if head is not None and manager is not None:
        session.add(
            OrgUnitManager(
                id=new_id(ORG_MANAGER_PREFIX),
                org_unit_id=head.id,
                user_id=manager.id,
                appointed_by=owner.id,
                created_at=_now(),
            )
        )
    await session.flush()
    return len(units)


async def _ensure_invite(session: AsyncSession) -> Invite:
    """The demo invitation, created once and reused on every later run."""
    workspace = await session.scalar(select(Workspace).where(Workspace.slug == WORKSPACE_SLUG))
    if workspace is None:
        raise RuntimeError(f"'{WORKSPACE_NAME}' 워크스페이스가 없습니다.")

    owner = await session.scalar(
        select(WorkspaceMembership).where(
            WorkspaceMembership.workspace_id == workspace.id,
            WorkspaceMembership.role == ROLE_OWNER,
        )
    )
    creator = await session.get(User, owner.user_id)
    invite = await invite_service.create_invite(
        session, workspace, creator, INVITED_EMAIL, ROLE_MEMBER
    )
    await session.commit()
    return invite


async def main() -> None:
    await create_all()
    async with SessionLocal() as session:
        result = await _seed(session)
        if result is None:
            print(f"'{WORKSPACE_NAME}' 워크스페이스가 이미 있어 데이터를 다시 만들지 않았습니다.")
            # The board is seeded on its own: a workspace that predates the
            # projects still gets them, and one that already has a board is
            # left alone.
            workspace = await session.scalar(
                select(Workspace).where(Workspace.slug == WORKSPACE_SLUG)
            )
            if workspace is not None:
                users = {user.name: user for user in (await session.scalars(select(User))).all()}
                channels = {
                    channel.name: channel
                    for channel in (await session.scalars(select(Channel))).all()
                }
                made = await _seed_projects(session, workspace, users, channels)
                milestones_made = await _seed_milestones(session, workspace)
                org_made = await _seed_org(session, workspace, users)
                await session.commit()
                if made:
                    print(f"  프로젝트 : {made}개 (데모 보드를 만들었습니다)")
                if milestones_made:
                    print(f"  마일스톤 : {milestones_made}개 (데모 마일스톤을 만들었습니다)")
                if org_made:
                    print(f"  조직     : {org_made}개 (데모 조직을 만들었습니다)")
        else:
            users_count, channels_count, messages_count = result
            print(f"'{WORKSPACE_NAME}' 워크스페이스를 만들었습니다.")
            print(f"  users    : {users_count}")
            print(f"  channels : {channels_count}")
            print(f"  messages : {messages_count}")
            print(f"  로그인   : {PEOPLE[0][1]} / {DEMO_PASSWORD}")
        invite = await _ensure_invite(session)
    print(f"  초대 이메일 : {INVITED_EMAIL}")
    print(f"  초대 코드   : {invite.token}")


if __name__ == "__main__":
    asyncio.run(main())
