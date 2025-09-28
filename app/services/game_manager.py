# app/services/game_manager.py

import asyncio
import json
from time import time
from app.protocol.message_models import *
from app.services.messaging import publish_message, end_game
from app.services.user_db import get_usernames_by_uids
from holdemlogic import RoundManager
from holdemlogic import Hand
from servers.history_logger import save_game_result


class GameManager:
    def __init__(self, 
                 game_id: str,
                 game_type: str, 
                 uids: list[str],
                 player_ids: list[str],
                 chips: list[int], 
                 sb: int = 1,
                 bb: int = 2,
                 base_time=15.0,
                 timebank=30.0, 
                 grace=1.0,
                 round_delay=5.0):
        self.game_id = game_id
        self.game_type = game_type
        assert len(player_ids) == len(chips)
        self.uids = uids
        self.player_ids = player_ids[:]
        self.chips = chips[:]
        self.n = len(player_ids)
        self.sb = sb
        self.bb = bb
        self.base_time = base_time
        self.timebank = timebank
        self.grace = grace
        self.round_delay = round_delay
        self.sb_index = 0
        self.rankings = []
        self.done = False
        self.sb_index = 0
        self.round_index = [None for _ in range(self.n)]
        self.round_index_to_game_index = []
        self.survived = [True] * self.n
        self.verbose = True
        self._start_time = time()
        self.deadline = 0.0

        self.action_count = 0  # ⏱️ 타이머 식별자
        self.is_sleeping = True
        def wake():
            self.is_sleeping = False
            return self._start_round()
        self.wake = wake


    def handle_action(self,
                      amount: int,
                      client_action_count: int,
                      received_at: float,
                      player_id: str = None,
                      is_timeout: bool = False,
                      ) -> list:
        self._print(f"[ACTION] received: {player_id=}, {amount=}, {is_timeout=}, {client_action_count=}, received_at={received_at:.2f}")
        messages = []
        
        if player_id is None:
            player_id = self.player_ids[self.round_index_to_game_index[self.round.get_current_player()]]
        
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
            deadline = self.round.deadline
            current_player = self.round.get_current_player()
            if not is_timeout and now > deadline:
                raise ValueError(f"⏱️ 행동 시간이 초과되었습니다. now={now:.2f}, deadline={deadline:.2f}")

            res = self.round.step(round_index, amount)
            self._print(f"[ACTION] step success: result = {res}")
            self.round.use_timebank(round_index, now=received_at)
            self._update_chips()

        except Exception as e:
            self._print(f"[ERROR] handle_action failed: {str(e)}")
            msg = ErrorMessage(
                type="error",
                game_id=self.game_id,
                player_id=player_id,
                payload=ErrorPayload(message=str(e))
            )
            messages += [msg]
            return messages

        if res["round_finished"]:
            messages += self._finish_round()
        else:
            self._start_turn()
            self._schedule_timeout_for_current_turn()
            messages += self._broadcast_state()

        if self.done:
            messages += self.end_game()
            
        return messages
        
    
    def _print(self, msg):
        if self.verbose:
            print(f"[GameManager {self.game_id:.4}] {msg}")


    def _setup_indices(self):
        self.survived = [self.chips[i] > 0 for i in range(self.n)]
        assert sum(self.survived) > 1
        while self.chips[self.sb_index] == 0:
            self.sb_index = (self.sb_index + 1) % self.n
        round_index = 0
        for i in (list(range(self.n))[self.sb_index:] + list(range(self.n))[:self.sb_index]):
            if self.survived[i]:
                self.round_index[i] = round_index
                round_index += 1
            else:
                self.round_index[i] = None
        self.round_index_to_game_index = [-1] * len([x for x in self.survived if x])
        for game_index in range(self.n):
            if self.round_index[game_index] is not None:
                round_index = self.round_index[game_index]
                self.round_index_to_game_index[round_index] = game_index
        self._print(f"{self.sb_index=}, {self.round_index=}, {self.round_index_to_game_index=}, {self.player_ids=}")


    def _start_round(self) -> list:
        messages = []
        self._print("starting new round")
        self._setup_indices()

        self.round = RoundManager(
            chips=[self.chips[i] for i in self.round_index_to_game_index if i != -1],
            sb=self.sb,
            bb=self.bb,
            base_time=self.base_time,
            timebank=self.timebank,
            grace=self.grace
        )
        self._update_chips()

        self._start_turn()  # ✅ action_count 증가 + round.start_turn 호출
        self._schedule_timeout_for_current_turn()  # ✅ 바로 타임아웃 예약
        messages += self._broadcast_state()
        
        return messages
        
    def _start_turn(self):
        self.action_count += 1
        self._print(f"[TURN] action_count incremented → {self.action_count}")
        round_index = self.round.get_current_player()
        self._print(f"[TURN] calling start_turn for round_index={round_index}")
        self.round.start_turn(round_index)
        
        
    def _schedule_timeout_for_current_turn(self):
        round_index = self.round.get_current_player()
        deadline = self.round.deadline
        grace = self.round.grace
        pid = self.player_ids[self.round_index_to_game_index[round_index]]
        
        self.deadline = deadline
        
    
    def _update_chips(self):
        for round_index, game_index in enumerate(self.round_index_to_game_index):
            self.chips[game_index] = self.round.chips[round_index]

            
    def _finish_round(self) -> list:
        messages = []
        self._print("round finished")
        distributions = self.round.get_distributions()
        
        for round_index, game_index in enumerate(self.round_index_to_game_index):
            self.chips[game_index] += distributions[round_index]
        self._update_rankings()
        
        messages += self._get_round_result()
        self.sb_index = (self.sb_index + 1) % self.n
        if len([chips for chips in self.chips if chips > 0]) > 1:
            self.action_count += 1
            self.deadline = time() + self.round_delay
            self.is_sleeping = True
            def wake():
                self.is_sleeping = False
                return self._start_round()
            self.wake = wake
        else:
            self.done = True
        
        return messages


    def end_game(self) -> list:
        messages = []
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
            messages += [msg]
        
        uid_to_pid = {uid: pid for uid, pid in zip(self.uids, self.player_ids)}
        rankings_uid = {uid: rankings[pid] for uid, pid in uid_to_pid.items()}
        save_game_result(
            game_id=self.game_id,
            game_type=self.game_type,
            player_uid_name_map=uid_to_pid,
            rankings=rankings_uid,
            duration=time() - self._start_time
        )
        
        return messages


    def _broadcast_state(self) -> list:
        messages = []
        for player_id in self.player_ids:
            messages += self._get_state(player_id)
        
        return messages


    def _get_state(self, player_id: str) -> list:
        messages = []
        now = time()
        j = self.player_ids.index(player_id)

        players = []
        for i in range(self.n):
            if not self.survived[i]:
                continue

            ridx = self.round_index[i]

            is_turn = (self.round.get_current_player() == ridx)
            deadline = self.round.deadline - self.grace
            time_before_deadline = deadline - now
            remaining_time = max(0, time_before_deadline - self.round.timebanks[ridx]) if is_turn else None
            timebank = min(self.round.timebanks[ridx], max(0, time_before_deadline)) if is_turn else self.round.timebanks[ridx]

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
        messages += [msg]
        
        return messages

    def _get_round_result(self) -> list:
        messages = []
        from holdemlogic import Hand
        board = self.round.get_board()
        
        distributions = self.round.get_distributions()
        self._print(f"distribution: {distributions}")
        contributions = self.round.get_contributions()
        survived = [i for i in range(len(self.survived)) if self.survived[i]]

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
                        payout=distributions[self.round_index[i]],
                        bet=contributions[self.round_index[i]],
                        change=(distributions[self.round_index[i]] - contributions[self.round_index[i]]),
                        hand="???",
                        hole_cards=["??", "??"]
                    ) for i in range(self.n) if self.survived[i]]
                )
            )
            if self.round.get_folded().count(False) == 1:
                i = self.player_ids.index(pid)
                if self.survived[i]:
                    msgidx = survived.index(i)
                    msg.payload.players[msgidx].hole_cards = list(map(lambda card: card.__repr__(),self.round.get_hole(self.round_index[i])))
            else:
                hands = self.round.get_hands()
                hand_names = [Hand.RANK_ORDER[hands[i].rank] for i in range(len(hands))]
                for i in range(self.n):
                    if self.survived[i] and not self.round.get_folded()[self.round_index[i]]:
                        msgidx = survived.index(i)
                        msg.payload.players[msgidx].hole_cards = list(map(lambda card: card.__repr__(),self.round.get_hole(self.round_index[i])))
                        msg.payload.players[msgidx].hand = hand_names[self.round_index[i]]
            messages += [msg]
        
        return messages

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
