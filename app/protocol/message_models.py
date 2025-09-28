# app/protocol/message_models.py

from pydantic import BaseModel, Field
from typing import List, Dict, Literal, Optional


class PlayerInfo(BaseModel):
    pid: str
    position: Optional[str]
    hole_cards: Optional[List[str]]
    folded: Optional[bool]
    chips: int
    bet: Optional[int]
    timebank: Optional[float] = None
    remaining_time: Optional[float] = None

class StatePayload(BaseModel):
    stage: str
    turn: str
    board: List[str]
    sb: int
    bb: int
    minraiseby: int
    players: List[PlayerInfo]
    action_count: int


class StateMessage(BaseModel):
    type: Literal["state_update"]
    game_id: str
    player_id: str
    payload: StatePayload


class RoundResultPlayerInfo(BaseModel):
    pid: str
    chips: int
    payout: Optional[int]
    bet: Optional[int]
    change: Optional[int]
    hand: Optional[str]
    hole_cards: Optional[List[str]]
    

class RoundResultPayload(BaseModel):
    board: List[str]
    players: List[RoundResultPlayerInfo]


class RoundResultMessage(BaseModel):
    type: Literal["round_result"]
    game_id: str
    player_id: str
    payload: RoundResultPayload


class GameEndPayload(BaseModel):
    rankings: dict[str, int]


class GameEndMessage(BaseModel):
    type: Literal["game_end"]
    game_id: str
    player_id: str
    payload: GameEndPayload


class ErrorPayload(BaseModel):
    message: str


class ErrorMessage(BaseModel):
    type: Literal["error"]
    game_id: str
    player_id: str
    payload: ErrorPayload


class MatchSuccessMessage(BaseModel):
    type: str = "match_success"
    game_id: str
    player_id: str
    uid: str
    

class LoginRequest(BaseModel):
    id: str
    password: str

class GoogleRegisterRequest(BaseModel):
    temp_token: str
    username: str

class GoogleLoginRequest(BaseModel):
    id_token: str
    
class InviteRequest(BaseModel):
    username: str  # 초대할 대상의 닉네임
    
class AcceptInviteRequest(BaseModel):
    leader_uid: str

class KickRequest(BaseModel):
    target_uid: str
    
class PromoteRequest(BaseModel):
    target_uid: str