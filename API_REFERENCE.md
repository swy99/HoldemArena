# API 명세서

## 개요

HoldemArena 플랫폼의 REST API 및 WebSocket 프로토콜 명세입니다.

## 인증

모든 인증이 필요한 API는 JWT 토큰을 사용합니다.

```
Authorization: Bearer <JWT_TOKEN>
```

## REST API 엔드포인트

### 🔐 인증 관련

#### 회원가입
```http
POST /api/register
Content-Type: application/json

{
  "id": "string",        // 3-20자, 소문자/숫자/_/- 만 허용
  "password": "string",  // 최소 8자
  "username": "string"   // 2-20자
}
```

#### 로그인
```http
POST /api/login
Content-Type: application/json

{
  "id": "string",
  "password": "string"
}
```

**응답**:
```json
{
  "access_token": "string",
  "token_type": "bearer",
  "uid": "string",
  "username": "string"
}
```

#### Google OAuth 로그인
```http
GET /api/google_login
```
Google OAuth 인증 페이지로 리디렉션됩니다.

#### Google 회원가입 완료
```http
POST /api/google_register
Content-Type: application/json

{
  "temp_token": "string",
  "username": "string"
}
```

#### 사용자 정보 조회
```http
GET /api/me
Authorization: Bearer <token>
```

**응답**:
```json
{
  "uid": "string",
  "username": "string",
  "provider": "local|google"
}
```

#### 계정 삭제
```http
POST /api/delete
Authorization: Bearer <token>
```

### 🎮 게임 관련

#### 빠른 게임 큐 참가
```http
POST /api/join_quick_play_queue
Authorization: Bearer <token>
```

#### 큐 떠나기
```http
POST /api/leave_queue
Authorization: Bearer <token>
```

#### 게임 히스토리 조회
```http
GET /api/game_history
Authorization: Bearer <token>
```

**응답**:
```json
{
  "history": [
    {
      "game_id": "string",
      "timestamp": "2024-01-01T00:00:00Z",
      "result": "win|lose",
      "chips_change": 100
    }
  ]
}
```

### 👥 파티 시스템

#### 파티 초대 수락
```http
POST /api/party/accept
Authorization: Bearer <token>
Content-Type: application/json

{
  "leader_uid": "string"
}
```

#### 파티 떠나기
```http
POST /api/party/leave
Authorization: Bearer <token>
```

#### 파티원 강퇴
```http
POST /api/party/kick
Authorization: Bearer <token>
Content-Type: application/json

{
  "target_uid": "string"
}
```

#### 파티장 위임
```http
POST /api/party/promote
Authorization: Bearer <token>
Content-Type: application/json

{
  "target_uid": "string"
}
```

### 🔍 유효성 검사

#### ID 중복 확인
```http
GET /api/check_id?id=example_id
```

#### 닉네임 중복 확인
```http
GET /api/check_username?username=example_name
```

## WebSocket 프로토콜

### 게임 WebSocket (포트 8000)

#### 연결
```
wss://holdemarena.win:8000/ws?token=<JWT_TOKEN>
```

#### 워커 시스템과의 연동
WebSocket 서버는 클라이언트와 워커 시스템 사이의 브리지 역할을 합니다:

```
클라이언트 → WebSocket 서버 → Redis 큐 → 워커
워커 → Redis Pub/Sub → WebSocket 서버 → 클라이언트
```

#### 메시지 형태

##### 1. 게임 상태 업데이트
```json
{
  "type": "state_update",
  "game_id": "string",
  "player_id": "string",
  "payload": {
    "stage": "preflop|flop|turn|river",
    "turn": "player_id",
    "board": ["Ah", "Kd", "Qc"],
    "sb": 1,
    "bb": 2,
    "minraiseby": 2,
    "players": [
      {
        "pid": "string",
        "position": "button|sb|bb",
        "hole_cards": ["As", "Ks"],
        "folded": false,
        "chips": 1000,
        "bet": 10,
        "timebank": 30.0,
        "remaining_time": 15.0
      }
    ],
    "action_count": 5
  }
}
```

##### 2. 라운드 결과
```json
{
  "type": "round_result",
  "game_id": "string",
  "player_id": "string",
  "payload": {
    "board": ["Ah", "Kd", "Qc", "Jh", "10s"],
    "players": [
      {
        "pid": "string",
        "chips": 1100,
        "payout": 100,
        "bet": 50,
        "change": 50,
        "hand": "Royal Flush",
        "hole_cards": ["As", "Ks"]
      }
    ]
  }
}
```

##### 3. 게임 종료
```json
{
  "type": "game_end",
  "game_id": "string",
  "player_id": "string",
  "payload": {
    "rankings": {
      "player1": 1,
      "player2": 2
    }
  }
}
```

##### 4. 매치 성공
```json
{
  "type": "match_success",
  "game_id": "string",
  "player_id": "string",
  "uid": "string"
}
```

##### 5. 오류 메시지
```json
{
  "type": "error",
  "game_id": "string",
  "player_id": "string",
  "payload": {
    "message": "Invalid action"
  }
}
```

#### 클라이언트 -> 서버 메시지

WebSocket 서버는 클라이언트 메시지를 받아 워커 큐로 전달합니다.

##### 게임 액션
```json
{
  "action": "fold|call|check|raise|allin",
  "amount": 100  // raise일 때만 필요
}
```

**처리 과정**:
1. WebSocket 서버가 클라이언트 액션 수신
2. `game_id % NUM_WORKERS`로 워커 결정
3. `game_step_handler_queue_{worker_id}`로 메시지 전송:
   ```json
   {
     "type": "action",
     "game_id": "abc123",
     "player_id": "p1",
     "action": "raise",
     "amount": 100,
     "action_count": 17,
     "received_at": 1748021321.53
   }
   ```

### 채팅 WebSocket (포트 7000)

#### 연결
```
wss://holdemarena.win:7000/chat?token=<JWT_TOKEN>
```

#### 메시지 형태

##### 채팅 메시지 전송
```json
{
  "type": "chat",
  "message": "Hello world!",
  "target": "lobby|game|party"
}
```

##### 파티 초대
```json
{
  "type": "invite",
  "username": "target_username"
}
```

### 파티 큐 WebSocket

#### 연결
```
wss://holdemarena.win:9000/quick_play_party_queue_ws?token=<JWT_TOKEN>
```

#### 파티 상태 업데이트
```json
{
  "type": "party_status",
  "party": {
    "members": [
      {
        "uid": "string",
        "username": "string",
        "is_leader": true
      }
    ],
    "in_queue": false
  }
}
```

## 에러 코드

| 코드 | 설명 |
|------|------|
| 400 | 잘못된 요청 (유효성 검사 실패) |
| 401 | 인증 실패 |
| 403 | 권한 없음 |
| 404 | 리소스를 찾을 수 없음 |
| 409 | 중복된 리소스 (ID/닉네임 중복) |
| 500 | 서버 내부 오류 |

## 워커 시스템 메시지 프로토콜

WebSocket 서버와 워커 시스템 간에 주고받는 메시지들입니다.

### 워커 큐 메시지

#### 게임 레지스트리 관리자 큐
```json
{
  "type": "init",
  "body": {
    "game_id": "abc123",
    "game_type": "quick_play",
    "uids": ["uid1", "uid2"],
    "player_ids": ["p1", "p2"],
    "room_settings": {
      "chips": [2000, 2000],
      "sb": 1,
      "bb": 2,
      "base_time": 15.0,
      "timebank": 30.0,
      "grace": 1.0,
      "round_delay": 5.0
    }
  }
}
```

#### 게임 스텝 핸들러 큐
```json
{
  "type": "action",
  "game_id": "abc123",
  "player_id": "p1",
  "action": "raise",
  "amount": 40,
  "action_count": 17,
  "received_at": 1748021321.53
}
```

```json
{
  "type": "send_state_to_user",
  "game_id": "abc123",
  "player_id": "p1"
}
```

#### 게임 타임아웃 디텍터 큐
```json
{
  "game_id": "abc123"
}
```

### outgoing_ws 큐 (워커 → WebSocket)
워커가 처리 결과를 WebSocket 서버로 전송하는 메시지들입니다.

```json
{
  "game_id": "abc123",
  "player_id": "p1",
  "message_type": "state_update",
  "payload": {
    "stage": "flop",
    "turn": "p2",
    "board": ["Ah", "Kd", "Qc"],
    "players": [...]
  }
}
```

## 데이터 모델

### PlayerInfo
```typescript
interface PlayerInfo {
  pid: string;
  position?: string;
  hole_cards?: string[];
  folded?: boolean;
  chips: number;
  bet?: number;
  timebank?: number;
  remaining_time?: number;
}
```

### StatePayload
```typescript
interface StatePayload {
  stage: "preflop" | "flop" | "turn" | "river";
  turn: string;
  board: string[];
  sb: number;
  bb: number;
  minraiseby: number;
  players: PlayerInfo[];
  action_count: number;
}
```

### RoundResultPlayerInfo
```typescript
interface RoundResultPlayerInfo {
  pid: string;
  chips: number;
  payout?: number;
  bet?: number;
  change?: number;
  hand?: string;
  hole_cards?: string[];
}
```

## 카드 표기법

카드는 다음 형식으로 표현됩니다:
- **숫자**: 2, 3, 4, 5, 6, 7, 8, 9, 10 (T), J, Q, K, A
- **무늬**: s (스페이드), h (하트), d (다이아몬드), c (클럽)
- **예시**: "As" (스페이드 에이스), "Kh" (하트 킹), "2c" (클럽 2)

## 게임 액션

| 액션 | 설명 |
|------|------|
| fold | 폴드 (카드 포기) |
| check | 체크 (베팅 없이 턴 넘기기) |
| call | 콜 (현재 베팅 액수에 맞추기) |
| raise | 레이즈 (베팅 올리기) |
| allin | 올인 (모든 칩 베팅) |

## 포지션

| 포지션 | 설명 |
|--------|------|
| button | 딜러 버튼 |
| sb | 스몰 블라인드 |
| bb | 빅 블라인드 |
| utg | 언더 더 건 |
| mp | 미들 포지션 |
| co | 컷오프 |