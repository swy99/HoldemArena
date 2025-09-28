# 기술 스택 상세

## 아키텍처 개요

HoldemArena는 **이중 계층 아키텍처**로 설계되었습니다:

1. **웹 서버 계층**: 사용자 인터페이스 및 실시간 통신 담당
2. **게임 워커 계층**: 순수 게임 로직 처리 및 분산 처리 담당

## Backend 기술 스택

### Core Framework
- **FastAPI**: 고성능 웹 프레임워크
  - 3개의 독립적인 서버 (로그인, WebSocket, 채팅)
  - 자동 OpenAPI 문서 생성
  - Pydantic을 통한 데이터 검증

### 분산 처리
- **Redis**: 메시지 큐 및 캐시 시스템
  - Lists를 이용한 워커 큐 (`BLPOP`/`RPUSH`)
  - Pub/Sub를 통한 실시간 브로드캐스팅
  - 게임 상태 캐싱
- **Python multiprocessing**: 워커 프로세스 관리
  - 워커당 독립적인 프로세스
  - `NUM_WORKERS` 환경변수로 확장 제어

### 데이터 저장
- **SQLite**: 영구 데이터 저장
  - 사용자 정보, 게임 히스토리
  - 가벼우면서도 ACID 보장
- **Redis**: 임시 데이터 및 캐시
  - 게임 상태, 파티 정보
  - 매치메이킹 큐

### 실시간 통신
- **WebSocket**: 양방향 실시간 통신
  - FastAPI WebSocket 지원
  - 자동 재연결 처리
- **Redis Pub/Sub**: 서버 간 메시지 전달
  - 워커에서 WebSocket 서버로 상태 전송
  - 다중 서버 환경 지원 가능

### 인증 시스템
- **JWT (JSON Web Tokens)**: 상태 없는 인증
  - `python-jose` 라이브러리 사용
  - 토큰 기반 세션 관리
- **Google OAuth2**: 소셜 로그인
  - 간편한 사용자 등록/로그인
  - 보안 강화

## Frontend 기술

### 클라이언트
- **Vanilla JavaScript**: 순수 자바스크립트
  - 외부 프레임워크 의존성 없음
  - WebSocket API 직접 활용
- **HTML5/CSS3**: 모던 웹 표준
  - 반응형 디자인
  - 카드 게임에 최적화된 UI

## 인프라 및 배포

### 웹 서버
- **Nginx**: 리버스 프록시 및 API 게이트웨이
  - SSL 종료
  - 경로별 라우팅 (/, /ws, /chat)
  - 정적 파일 서빙
  - WebSocket 프록시 지원

### 프로세스 관리
- **systemd**: 프로덕션 환경 프로세스 관리
  - 자동 재시작
  - 로그 관리
  - 의존성 관리

### SSL/보안
- **Let's Encrypt**: 무료 SSL 인증서
  - 자동 갱신
  - HTTPS 강제

## 게임 엔진 기술

### 포커 로직 구현
```python
# holdemlogic/ 모듈 구조
├── card.py          # 카드 및 덱 클래스
├── hand.py          # 핸드 평가 및 랭킹 시스템
├── bet_manager.py   # 베팅 시스템 및 포지션 관리
└── round_manager.py # 라운드 진행 및 타이머 관리
```

### 핵심 알고리즘
- **핸드 평가**: 7장 중 최고 5장 조합 계산
- **사이드팟**: 복잡한 올인 상황 처리
- **베팅 검증**: 포커 규칙에 따른 액션 유효성 검사

## 분산 시스템 설계

### 워커 분산 알고리즘
```python
# 일관된 해싱을 통한 게임 분산
worker_id = game_id % NUM_WORKERS
```

### 메시지 큐 시스템
- **워커별 전용 큐**: 경합 최소화
- **비동기 처리**: BLPOP을 통한 논블로킹 큐 처리
- **메시지 타입별 라우팅**: 게임 생성, 액션 처리, 타임아웃 감지

### 3-루프 워커 구조
```python
# servers/worker.py
async def worker_main(i: int):
    await asyncio.gather(
        game_registry_manager_loop(i),    # 게임 생성/삭제
        game_step_handler_loop(i),        # 게임 액션 처리
        game_timeout_detector_loop(i),    # 타임아웃 감지
    )
```

## 성능 및 확장성

### 성능 최적화
- **비동기 처리**: asyncio를 통한 동시 처리
- **커넥션 풀링**: Redis 연결 재사용
- **메시지 배치 처리**: 여러 상태 변경 묶어서 전송

### 확장성 설계
- **수평 확장**: 워커 수 증가로 처리 능력 확장
- **무상태 워커**: 워커 간 의존성 없음
- **독립적 스케일링**: 웹서버와 워커 별도 확장

### 모니터링
- **구조화된 로깅**: 워커별, 서비스별 로그 분리
- **메트릭 수집**: Redis를 통한 실시간 상태 추적
- **헬스체크**: 각 컴포넌트별 상태 모니터링

## 데이터 모델

### Redis 키 구조
```
# 게임 상태
user:{uid}:game                    # 사용자의 현재 게임 ID
game:{game_id}:player:{pid}:uid    # 플레이어-유저 매핑

# 큐 시스템
game_registry_manager_queue_{i}    # 게임 생성/삭제 큐
game_step_handler_queue_{i}        # 게임 액션 처리 큐
outgoing_ws                        # WebSocket 브로드캐스트 큐

# 파티 시스템
party:{party_id}:members           # 파티 멤버 목록
party:{party_id}:leader            # 파티장 정보
```

### SQLite 스키마
- **users**: 사용자 기본 정보 (id, username, provider)
- **game_history**: 게임 결과 기록
- **friendships**: 친구 관계

## 보안 고려사항

### 인증/인가
- JWT 토큰 기반 상태 없는 인증
- 토큰 만료 시간 관리
- Google OAuth2를 통한 보안 강화

### 네트워크 보안
- HTTPS 강제 (HTTP → HTTPS 리디렉션)
- WebSocket Secure (WSS) 지원
- CORS 정책 적용

### 데이터 보안
- 패스워드 해싱 (bcrypt)
- SQL 인젝션 방지 (Pydantic 검증)
- Redis AUTH를 통한 접근 제어

## 개발 환경

### 의존성 관리
- **requirements.txt**: 정확한 버전 명시
- **가상환경**: 격리된 Python 환경
- **환경변수**: `.env` 파일을 통한 설정 관리

### 테스트
- **단위 테스트**: `app/tests/` 디렉토리
- **게임 로직 테스트**: 포커 엔진 검증
- **통합 테스트**: 전체 플로우 검증

이 기술 스택은 실제 프로덕션 환경에서 안정적으로 운영 가능하도록 설계되었습니다.