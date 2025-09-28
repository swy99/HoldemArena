# holdemlogic/round_manager.py

from .bet_manager import BetManager
from .card import Deck
from .hand import Hand, HandRanking
import time

class RoundManager:
    def __init__(self, chips: list[int], sb=1, bb=2, base_time=15.0, timebank=30.0, grace=1.0):
        self.bm = BetManager(chips[:], sb, bb)
        self.n = len(chips)
        self.chips = self.bm.chips[:]
        self.deck = Deck()
        self.burnt = []
        self.board = []
        self.hole = [[] for _ in range(self.n)]
        self.debug = False

        # ⏱️ 타이머 관련 필드
        self.base_time = base_time
        self.timebanks = [timebank for _ in range(self.n)]
        self.deadline = 0.0
        self.grace = grace

        self._deal_hole()

    def start_turn(self, i: int):
        now = time.time()
        self.deadline = now + self.base_time + self.timebanks[i] + self.grace
        print(f"[RoundManager] start_turn({i}) → deadline set to {self.deadline:.2f} (now={now:.2f}, timebank={self.timebanks[i]:.2f})")

    def use_timebank(self, i: int, now: float):
        elapsed = now - self.deadline - self.grace
        overflow = elapsed - self.base_time
        if overflow > 0:
            self.timebanks[i] = max(0.0, self.timebanks[i] - overflow)
            
    def _deal_hole(self):
        for i in range(self.n):
            self.hole[i] += self.deck.draw(2)
        if self.debug:
            print(self.hole)
            
    
    def _number_of_cards_on_board(self):
        stage = self.bm.current_stage()
        if stage == 0: # preflop
            return 0
        elif stage == 1: # flop
            return 3
        elif stage == 2: # turn
            return 4
        else: # river/showdown
            return 5
        
    
    def current_player(self):
        return self.bm.current_player()
    
    
    def is_done(self):
        return self.bm.finished
    
    
    def get_hole(self, idx):
        return self.hole[idx][:]
    
    
    def get_board(self):
        return self.board[:]
    
    
    def get_contributions(self):
        return self.bm.contributions[:]
    
    
    def get_folded(self):
        return self.bm.folded[:]
    
    
    def get_current_player(self):
        return self.bm.current_player()
    
    
    def get_current_stage(self):
        return self.bm.current_stage()
    
    
    def get_stages(self):
        return self.bm.stages[:]
    
    
    def get_distributions(self):
        return self._distribute()
    
    
    def get_hands(self):
        assert self.bm.finished
        hands = {i: Hand(self.hole[i] + self.board) for i in range(self.n)}
        return hands
    
        
    def step(self, player_idx: int, amt: int) -> dict:
        assert player_idx == self.current_player(), f"차례가 아닙니다"

        finished, i, contributions, folded = self.bm.step(amt)
        self.chips = self.bm.chips[:]

        drawn_cards = []
        if self.get_folded().count(False) > 1:
            target_board_size = self._number_of_cards_on_board()

            
            while len(self.board) < target_board_size:
                card = self.deck.draw()
                self.board.append(card)
                drawn_cards.append(card)

        return {
            "round_finished": finished,
            "stage_advanced": len(drawn_cards) > 0,
            "card_drawn": len(drawn_cards) > 0,
            "drawn_cards": drawn_cards,
            "next_player": None if finished else self.bm.current_player()
        }
                
    
    def _distribute(self):
        distributions = [0 for i in range(self.n)]
        if self.get_folded().count(False) == 1:
            return [0 if self.get_folded()[i] else sum(self.bm.contributions) for i in range(self.n)]
        hands = {i: Hand(self.hole[i] + self.board) for i in range(self.n)}
        # 핸드 비교 및 순위 결정
        result = HandRanking.rank_players(hands)
        contributions = self.bm.contributions[:]
        if self.debug:
            print(contributions)
            print("result: ", result)
        while sum(contributions) > 0:
            strongest_hands = result.pop(0)
            winners = [i for i in strongest_hands if not self.bm.folded[i]]
            winners_contributions = {i: contributions[i] for i in winners}
            while sum(winners_contributions.values()) > 0:
                mincon_nonzero = min(x for x in winners_contributions.values() if x != 0)
                pie_winners = [i for i in winners if winners_contributions[i] > 0]
                num_pie_winners = len(pie_winners)
                pie = sum([min(contributions[i], mincon_nonzero) for i in range(self.n)])
                for i in range(self.n):
                    contributions[i] -= min(contributions[i], mincon_nonzero)
                pie_per_person = int(pie / num_pie_winners)
                for i in pie_winners:
                    distributions[i] += pie_per_person
                    winners_contributions[i] -= mincon_nonzero
                leftover_pie = pie - pie_per_person * num_pie_winners
                for i in sorted(pie_winners):
                    if leftover_pie == 0:
                        break
                    distributions[i] += 1
                    leftover_pie -= 1
        if self.debug:
            print(distributions)
        return distributions