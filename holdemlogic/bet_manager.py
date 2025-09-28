# holdemlogic/bet_manager.py

class BetManager:
    def __init__(self, chips: list[int], sb=1, bb=2):
        n = len(chips)
        assert 2 <= n and n <= 8
        assert bb >= sb
        for i in range(n):
            assert chips[i] > 0
        self.n = n
        self.chips = chips[:]
        self.sb = sb
        self.bb = bb
        self.folded = [False for _ in range(n)]
        self.min_raise_by = bb
        self.stages = ["Preflop", "Flop", "Turn", "River"]
        self.positions = {
            2:  ["SB", "BB"],
            3:  ["SB", "BB", "BTN"],
            4:  ["SB", "BB", "UTG", "HJ"],
            5:  ["SB", "BB", "UTG", "MP", "CO"],
            6:  ["SB", "BB", "UTG", "MP", "HJ", "CO"],
            7:  ["SB", "BB", "UTG", "UTG+1", "MP", "HJ", "CO"],
            8:  ["SB", "BB", "UTG", "UTG+1", "MP", "MP+1", "HJ", "CO"],
        }[n]
        self.stage = 0
        self.finished = False
        self.i = 0 if n == 2 else 2 # 헤즈업일 경우 프리플랍 SB 먼저, 3인이상 UTG 먼저
        self.contributions = [0 for _ in range(n)]
        self.dead_raise = False
        self.action_cnt = [0 for _ in range(n)]
        self._force_blind_bets()
        self.debug = False
    
    
    def _force_blind_bets(self):
        if self.chips[0] >= self.sb:
            self.contributions[0] += self.sb
            self.chips[0] -= self.sb
        else:
            self.contributions[0] += self.chips[0]
            self.chips[0] = 0
            
        if self.chips[1] >= self.bb:
            self.contributions[1] += self.bb
            self.chips[1] -= self.bb
        else:
            self.contributions[1] += self.chips[1]
            self.chips[1] = 0
    
    
    def step(self, amt):
        self._apply_amt(amt)
        self._find_next_player() #다음 플레이어 찾고 필요할 경우 다음 베팅라운드로 넘어감
        return self.finished, self.i, self.contributions, self.folded
        
        
    def _find_next_player(self):
        not_folded = 0
        not_all_in = 0
        for i in range(self.n):
            if not self.folded[i]:
                not_folded += 1
                if self.chips[i] > 0:
                    not_all_in += 1
        if not_folded == 1: # 폴드로 인한 조기종료
            if self.debug:
                print("폴드로 인한 조기종료")
            self.finished = True
            return
        if not_all_in == 0: # 올인으로 인한 조기종료
            if self.debug:
                print("올인으로 인한 조기종료")
            self.finished = True
            return
        undone = []
        for i in range(self.n):
            if not self.folded[i] and self.chips[i] > 0 and (self.contributions[i] < max(self.contributions) or self.action_cnt[i] == 0):
                undone.append(i)
        if len(undone) > 0:
            while self.folded[self.i] or self.chips[self.i] == 0 or (self.contributions[self.i] == max(self.contributions) and self.action_cnt[self.i] > 0):
                self.i += 1
                self.i %= self.n
            return
        if self.stage == 3: # 쇼다운
            if self.debug:
                print("<쇼다운>")
            self.finished = True
            return
        else: # 다음라운드로
            self.stage += 1
            if self.debug:
                print(f"<{self.stages[self.stage]} 시작>")
            self.min_raise_by = self.bb
            self.i = 1 if self.n == 2 else 0 # 헤즈업일경우 BB부터, 3인이상 SB부터
            while self.folded[self.i] or self.chips[self.i] == 0:
                self.i += 1
                self.i %= self.n
            self.dead_raise = False
            for i in range(self.n):
                self.action_cnt[i] = 0            
            if not_all_in == 1:
                if self.debug:
                    print("올인으로 인한 조기종료")
                self.finished = True
                return
            
    
    def current_player(self):
        return self.i if not self.finished else None
    
    
    def current_stage(self):
        return self.stage if not self.finished else 4
    

    def _apply_amt(self, amt):
        assert amt >= 0, "음수 베팅 불가"
        assert self.chips[self.i] >= amt, "가진 칩보다 많이 베팅 불가"
        if amt == 0:
            if self.contributions[self.i] < max(self.contributions): # 폴드
                if self.debug:
                    print("폴드")
                self.folded[self.i] = True
                return
            else: # 체크
                if self.debug:
                    print("체크")
                self.action_cnt[self.i] += 1
                return
        to_call = max(self.contributions) - self.contributions[self.i]
        if amt == to_call: # 콜
            if self.debug:
                print("콜")
            self.contributions[self.i] += amt
            self.chips[self.i] -= amt
            self.action_cnt[self.i] += 1
            return
        if amt < to_call: #올인콜
            if self.debug:
                print("올인콜")
            assert amt == self.chips[self.i], f"{amt}는 콜하기 위한 최소 칩({to_call}) 보다 적습니다"
            self.contributions[self.i] += amt
            self.chips[self.i] = 0
            return
        # 레이즈/벳
        assert not self.dead_raise, "이미 데드레이즈가 있는 베팅라운드에서는 더이상 레이즈할 수 없습니다"
        raise_by = amt - to_call
        if raise_by >= self.min_raise_by: # 풀레이즈
            if self.debug:
                print("풀레이즈")
            self.min_raise_by = max(raise_by, self.min_raise_by)
            self.contributions[self.i] += amt
            self.chips[self.i] -= amt
            self.action_cnt[self.i] += 1
            return
        else: # 데드레이즈(올인)
            assert False, f"데드레이즈는 허용되지 않습니다."
            if self.debug:
                print("데드레이즈")
            assert amt == self.chips[self.i], f"{amt}는 레이즈하기 위한 최소배팅({self.min_raise_by + to_call})보다 적습니다"
            self.contributions[self.i] += amt
            self.chips[self.i] = 0
            self.dead_raise = True
            return
        
    def _current_state(self):
        return f"[{self.stages[self.stage]}/{self.positions[self.i]}] bets: {self.contributions}   chips: {self.chips}   folded: {self.folded}   act cnt: {self.action_cnt}"
        
        