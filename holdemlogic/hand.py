# holdemlogic/hand.py

from collections import Counter
from itertools import combinations
from .card import Card, Deck

class Hand:
    RANK_ORDER = [
        "High Card", "One Pair", "Two Pair", "Three of a Kind", "Straight",
        "Flush", "Full House", "Four of a Kind", "Straight Flush", "Royal Flush"
    ]

    def __init__(self, cards: list):
        self.cards = cards
        self.rank, self.best_hand = self.evaluate_hand()
    
    def __str__(self):
        card_str = [str(c) for c in self.best_hand]
        return f"[{', '.join(card_str)}] → {Hand.RANK_ORDER[self.rank]}"


    def evaluate_hand(self) -> tuple:
        best_rank = -1
        best_hand = None
        for combo in combinations(self.cards, 5):
            rank = self.classify_hand(combo)
            if best_rank < rank or (best_rank == rank and self.compare_kickers(combo, best_hand) > 0):
                best_rank = rank
                best_hand = combo
        return best_rank, sorted(best_hand, key=lambda c: c.rank_value(), reverse=True)

    def classify_hand(self, cards: tuple) -> int:
        suits = [c.suit for c in cards]
        ranks = sorted([c.rank for c in cards], key=lambda r: "23456789TJQKA".index(r), reverse=True)
        rank_counts = Counter(ranks)
        count_values = sorted(rank_counts.values(), reverse=True)
        is_flush = len(set(suits)) == 1

        rank_indexes = sorted(["23456789TJQKA".index(r) for r in set(ranks)], reverse=True)
        is_straight = len(rank_indexes) >= 5 and all(
            rank_indexes[i] - 1 == rank_indexes[i + 1] for i in range(4)
        )

        if is_flush and set(ranks) >= set(['T', 'J', 'Q', 'K', 'A']):
            return 9  # Royal Flush
        if is_flush and is_straight:
            return 8  # Straight Flush
        if count_values == [4, 1]:
            return 7  # Four of a Kind
        if count_values == [3, 2]:
            return 6  # Full House
        if is_flush:
            return 5  # Flush
        if is_straight:
            return 4  # Straight
        if count_values == [3, 1, 1]:
            return 3  # Three of a Kind
        if count_values == [2, 2, 1]:
            return 2  # Two Pair
        if count_values == [2, 1, 1, 1]:
            return 1  # One Pair
        return 0  # High Card

    def compare_kickers(self, hand1, hand2) -> int:
        if not hand2:
            return 1
        h1 = sorted(hand1, key=lambda c: c.rank_value(), reverse=True)
        h2 = sorted(hand2, key=lambda c: c.rank_value(), reverse=True)
        for c1, c2 in zip(h1, h2):
            if c1.rank_value() > c2.rank_value():
                return 1
            elif c1.rank_value() < c2.rank_value():
                return -1
        return 0

    def __lt__(self, other):
        if self.rank != other.rank:
            return self.rank < other.rank
        return self.compare_kickers(self.best_hand, other.best_hand) < 0

    def __eq__(self, other):
        return self.rank == other.rank and self.compare_kickers(self.best_hand, other.best_hand) == 0

    def __repr__(self):
        return f"{Hand.RANK_ORDER[self.rank]}: {self.best_hand}"


class HandRanking:
    @staticmethod
    def rank_players(player_hands: dict) -> list:
        """
        플레이어 ID와 Hand 객체 딕셔너리를 받아 등수 그룹별로 나눈다.
        Returns: list[list[player_id]] 형태 (ex. [["A"], ["B", "C"], ["D"]])
        """
        sorted_entries = sorted(player_hands.items(), key=lambda x: x[1], reverse=True)
        grouped = []
        current_group = [sorted_entries[0][0]]
        current_hand = sorted_entries[0][1]

        for pid, hand in sorted_entries[1:]:
            if hand == current_hand:
                current_group.append(pid)
            else:
                grouped.append(current_group)
                current_group = [pid]
                current_hand = hand
        grouped.append(current_group)
        return grouped


if __name__ == "__main__":
    def test_random_hands():
        print("\n[TEST] 무작위 핸드 비교 테스트")
        deck = Deck()
        board = deck.draw(5)
        print("커뮤니티 카드:", board)

        players = {}
        for name in ["Alice", "Bob", "Charlie", "Diana"]:
            hole_cards = deck.draw(2)
            hand = Hand(hole_cards + board)
            players[name] = hand
            print(f"{name}: {hole_cards} -> {hand}")

        result = HandRanking.rank_players(players)
        print(result)
        print("\n등수 결과:")
        for i, group in enumerate(result, 1):
            print(f"{i}등: {group}")

    test_random_hands()
