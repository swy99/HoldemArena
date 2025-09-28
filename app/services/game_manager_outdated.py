# app/services/game_manager.py

from app.protocol.message_models import *
from app.services.messaging import publish_message, end_game
from app.services.user_db import get_usernames_by_uids
from holdemlogic import RoundManager
from holdemlogic import Hand
from time import time
import asyncio
from typing import Callable
from app.services.messaging import ar  # redis.asyncio.Redis
import json
from app.services.history_logger import save_game_result


class GameManager:
    def __init__(self, game_id: str, game_type: str, uids: list[str], player_ids: list[str], chips: list[int], sb: int = 1, bb: int = 2, save_callback: Callable = None, base_time=15.0, timebank=30.0, grace=1.0):
        self.game_id = game_id
        self.game_type = game_type
        assert len(player_ids) == len(chips)
        self.uids = uids
        self.player_ids = player_ids[:]
        self.chips = chips[:]
        self.n = len(player_ids)
        self.sb = sb
        self.bb = bb
        self._save_callback = save_callback
        self.base_time = base_time
        self.timebank = timebank
        self.grace = grace
        self.sb_index = 0
        self.rankings = []
        self.done = False
        self.sb_index = 0
        self.round_index = [None for _ in range(self.n)]
        self.round_index_to_game_index = []
        self.survived = [True] * self.n
        self.verbose = True
        self._start_time = time()

        self.action_count = 0  # ⏱️ 타이머 식별자
        self._start_round()
        
    
    def _print(self, msg):
        if self.verbose:
            print(f"[GameManager gid={self.game_id[:5]}...] {msg}")


    def _save(self):
        if self._save_callback:
            self._save_callback(self)


    def _setup_indices(self):
        self.survived = [self.chips[i] > 0 for i in range(self.n)]
        assert sum(self.survived) > 1
        while self.chips[self.sb_index] == 0:
            self.sb_index = (self.sb_index + 1) % self.n
        round_index = 0
        for i in (list(range(self.n))[self.sb_index:] + list(range(self.n))[:self.sb_index]):
            if self.chips[i] > 0:
                self.round_index[i] = round_index
                round_index += 1
        self.round_index_to_game_index = [-1] * len(self.survived)
        for game_index in range(self.n):
            if self.round_index[game_index] is not None:
                round_index = self.round_index[game_index]
                self.round_index_to_game_index[round_index] = game_index


    def _start_round(self):
        self._print("starting new round")
        self._setup_indices()

        self.round = RoundManager(
            chips=[self.chips[i] for i in self.round_index_to_game_index],
            sb=self.sb,
            bb=self.bb,
            base_time=self.base_time,
            timebank=self.timebank,
            grace=self.grace
        )
        self._update_chips()

        self._start_turn()  # ✅ action_count 증가 + round.start_turn 호출
        self._schedule_timeout_for_current_turn()  # ✅ 바로 타임아웃 예약

        self._broadcast_state()
        self._save()
        
    def _start_turn(self):
        self.action_count += 1
        self._print(f"[TURN] action_count incremented → {self.action_count}")
        round_index = self.round.get_current_player()
        self._print(f"[TURN] calling start_turn for round_index={round_index}")
        self.round.start_turn(round_index)
        
        
    def _schedule_timeout_for_current_turn(self):
        round_index = self.round.get_current_player()
        deadline = self.round.deadlines[round_index]
        grace = self.round.grace
        pid = self.player_ids[self.round_index_to_game_index[round_index]]

        self._print(f"[SCHEDULE] timeout for {pid}: deadline={deadline:.2f}, grace={grace:.2f}, action_count={self.action_count}")

        # ✅ Redis PubSub으로 timeout 예약 요청
        asyncio.create_task(ar.publish("game_timeouts", json.dumps({
            "game_id": self.game_id,
            "player_id": pid,
            "deadline": deadline + grace,
            "action_count": self.action_count
        })))
        
    
    def _update_chips(self):
        for round_index, game_index in enumerate(self.round_index_to_game_index):
            self.chips[game_index] = self.round.chips[round_index]


    async def handle_action(self, player_id: str, amount: int, ignore_timeout_check: bool = False, client_action_count: int = None):
        self._print(f"[ACTION] received: pid={player_id}, amt={amount}, ignore_timeout={ignore_timeout_check}, client_action_count={client_action_count} 실행 시각: {time():.2f}")
        
        try:
            game_index = self.player_ids.index(player_id)
            round_index = self.round_index[game_index]

            if round_index is None:
                raise ValueError("라운드에 참여 중인 플레이어가 아님")

            # ✅ action_count 검증
            self._print(f"[ACTION] current action_count = {self.action_count}, received client_action_count = {client_action_count}")
            if client_action_count is not None and client_action_count != self.action_count:
                raise ValueError(f"⏱️ 현재 유효하지 않은 액션입니다 (구버전 상태). action_count mismatch: expected={self.action_count}, got={client_action_count}")

            now = time()
            deadline = self.round.deadlines[round_index]
            current_player = self.round.get_current_player()

            self._print(f"[ACTION] turn check: round_index={round_index}, current_player={current_player}")
            self._print(f"[ACTION] time check: now={now:.2f}, deadline={deadline:.2f}, diff={now - deadline:.2f}")

            if not ignore_timeout_check and now > deadline:
                raise ValueError(f"⏱️ 행동 시간이 초과되었습니다. now={now:.2f}, deadline={deadline:.2f}")

            res = self.round.step(round_index, amount)
            self._print(f"[ACTION] step success: result = {res}")
            self.round.use_timebank(round_index)
            self._update_chips()

        except Exception as e:
            self._print(f"[ERROR] handle_action failed: {str(e)}")
            msg = ErrorMessage(
                type="error",
                game_id=self.game_id,
                player_id=player_id,
                payload=ErrorPayload(message=str(e))
            )
            publish_message(msg)
            return

        if res["round_finished"]:
            await self._finish_round()
        else:
            self._start_turn()
            self._schedule_timeout_for_current_turn()
            self._broadcast_state()
        self._save()

        if self.done:
            await self.end_game()

            
    async def _finish_round(self):
        self._print("round finished")
        distributions = self.round.get_distributions()
        
        for round_index, game_index in enumerate(self.round_index_to_game_index):
            self.chips[game_index] += distributions[round_index]
        self._update_rankings()
        
        self._send_round_result()
        self.sb_index = (self.sb_index + 1) % self.n
        if len([chips for chips in self.chips if chips > 0]) > 1:
            round_delay_sec = 5
            from asyncio import sleep
            self._print(f"waiting {round_delay_sec} seconds for clients to see roundresults")
            await sleep(round_delay_sec)
            self._start_round()
        else:
            self.done = True


    async def end_game(self):
        for i in range(self.n):
            if self.chips[i] > 0:
                self.rankings.insert(0, [self.player_ids[i]])
                break
        i = 1
        rankings = {}
        for group in self.rankings:
            for pid in group:
                rankings[pid] = i
            i += len(group)

        self._print(f"end: ranking = {self.rankings} / {rankings}")
        for i in range(self.n):
            pid = self.player_ids[i]
            msg = GameEndMessage(
                type="game_end",
                game_id=self.game_id,
                player_id=pid,
                payload=GameEndPayload(
                    rankings=rankings
                )
            )
            publish_message(msg)
        from asyncio import sleep
        self._print(f"sleeping before ending game")
        uid_to_pid = {uid: pid for uid, pid in zip(self.uids, self.player_ids)}
        rankings_uid = {uid: rankings[pid] for uid, pid in uid_to_pid.items()}
        await sleep(5)
        save_game_result(
            game_id=self.game_id,
            game_type=self.game_type,
            player_uid_name_map=uid_to_pid,
            rankings=rankings_uid,
            duration=time() - self._start_time
        )
        end_game(self.game_id)


    def _broadcast_state(self):
        for player_id in self.player_ids:
            self._send_state(player_id)


    def _send_state(self, player_id: str):
        self._print(f"requesting sending states to player{player_id}")

        now = time()
        j = self.player_ids.index(player_id)

        players = []
        for i in range(self.n):
            if not self.survived[i]:
                continue

            ridx = self.round_index[i]

            is_turn = (self.round.get_current_player() == ridx)
            deadline = self.round.deadlines[ridx]
            remaining_time = max(0, deadline - now - self.round.timebanks[ridx]) if is_turn else None
            timebank = self.round.timebanks[ridx] if (remaining_time is None or remaining_time > 0) else (deadline - now)

            hole_cards = ["??", "??"]
            if i == j:  # 내가 볼 때 내 홀카드는 공개
                hole_cards = list(map(lambda card: card.__repr__(), self.round.get_hole(ridx)))

            players.append(PlayerInfo(
                pid=self.player_ids[i],
                position=self.round.bm.positions[ridx],
                hole_cards=hole_cards,
                folded=self.round.get_folded()[ridx],
                chips=self.chips[i],
                bet=self.round.bm.contributions[ridx],
                timebank=round(timebank, 2),
                remaining_time=round(remaining_time, 2) if remaining_time is not None else None
            ))

        msg = StateMessage(
            type="state_update",
            game_id=self.game_id,
            player_id=player_id,
            payload=StatePayload(
                stage=self.round.get_stages()[self.round.get_current_stage()],
                turn=self.player_ids[self.round_index_to_game_index[self.round.get_current_player()]],
                board=list(map(lambda card: card.__repr__(), self.round.get_board())),
                sb=self.sb,
                bb=self.bb,
                minraiseby=self.round.bm.min_raise_by,
                players=players,
                action_count=self.action_count
            )
        )

        publish_message(msg)

    def _send_round_result(self):
        from holdemlogic import Hand
        board = self.round.get_board()
        
        distributions = self.round.get_distributions()
        self._print(f"distribution: {distributions}")
        contributions = self.round.get_contributions()

        for pid in self.player_ids:
            msg = RoundResultMessage(
                type="round_result",
                game_id=self.game_id,
                player_id=pid,
                payload=RoundResultPayload(
                    board=list(map(lambda card: card.__repr__(), board)),
                    players=[RoundResultPlayerInfo(
                        pid=self.player_ids[i],
                        chips=self.chips[i],
                        payout=distributions[self.round_index[i]] if self.survived[i] else None,
                        bet=contributions[self.round_index[i]] if self.survived[i] else None,
                        change=(distributions[self.round_index[i]] - contributions[self.round_index[i]]) if self.survived[i] else None,
                        hand="???" if self.survived[i] else None,
                        hole_cards=["??", "??"] if self.survived[i] else None 
                    ) for i in range(self.n)]
                )
            )
            if self.round.get_folded().count(False) == 1:
                i = self.player_ids.index(pid)
                if self.survived[i]:
                    msg.payload.players[i].hole_cards = list(map(lambda card: card.__repr__(),self.round.get_hole(self.round_index[i])))
            else:
                hands = self.round.get_hands()
                hand_names = [Hand.RANK_ORDER[hands[i].rank] for i in range(len(hands))]
                for i in range(self.n):
                    if self.survived[i] and not self.round.get_folded()[self.round_index[i]]:
                        msg.payload.players[i].hole_cards = list(map(lambda card: card.__repr__(),self.round.get_hole(self.round_index[i])))
                        msg.payload.players[i].hand = hand_names[self.round_index[i]]
            publish_message(msg)

    def _update_rankings(self):
        eliminated = [
            pid for pid, chip in zip(self.player_ids, self.chips)
            if chip == 0 and pid not in str(self.rankings)
        ]
        if eliminated:
            self.rankings.insert(0, eliminated)

    def get_positions(self) -> dict:
        n = len(self.player_ids)
        table = {
            2: ["SB", "BB"],
            3: ["SB", "BB", "BTN"],
            4: ["SB", "BB", "UTG", "BTN"],
            5: ["SB", "BB", "UTG", "CO", "BTN"],
            6: ["SB", "BB", "UTG", "MP", "CO", "BTN"],
            7: ["SB", "BB", "UTG", "UTG+1", "MP", "CO", "BTN"],
            8: ["SB", "BB", "UTG", "UTG+1", "MP", "MP+1", "CO", "BTN"]
        }
        names = table[n]
        return {
            pid: names[i] for i, pid in enumerate(self.player_ids)
        }
