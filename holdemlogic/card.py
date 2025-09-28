# holdemlogic/card.py

class Card:
    SUITS = ['♠', '♥', '♦', '♣']  # 스페이드, 하트, 다이아, 클로버
    RANKS = ['2', '3', '4', '5', '6', '7', '8', '9', 'T', 'J', 'Q', 'K', 'A']  # T는 10

    def __init__(self, suit: str, rank: str):
        if suit in ['S', 'H', 'D', 'C']:
            suit = ['♠', '♥', '♦', '♣'][['S', 'H', 'D', 'C'].index(suit)]
        if suit in ['s', 'h', 'd', 'c']:
            suit = ['♠', '♥', '♦', '♣'][['s', 'h', 'd', 'c'].index(suit)]
        if rank == '10':
            rank = 'T'
        if rank.isalpha():
            rank = rank.upper()
        assert suit in Card.SUITS, f"Invalid suit: {suit}"
        assert rank in Card.RANKS, f"Invalid rank: {rank}"
        self.suit = suit
        self.rank = rank

    def __repr__(self):
        return f"{self.rank}{self.suit}"

    def rank_value(self):
        # 숫자 비교용 값
        return Card.RANKS.index(self.rank)

    def __lt__(self, other):
        return self.rank_value() < other.rank_value()

    def __eq__(self, other):
        return self.rank == other.rank and self.suit == other.suit




import random

class Deck:
    def __init__(self):
        self.cards = [Card(suit, rank) for suit in Card.SUITS for rank in Card.RANKS]
        self.shuffle()

    def shuffle(self):
        random.shuffle(self.cards)

    def draw(self, count=1):
        assert len(self.cards) >= count, "Not enough cards left in the deck"
        assert count > 0
        if count > 1:
            picked = random.sample(self.cards, count)
            self.cards = [x for x in self.cards if x not in picked]
            return picked
            
        else:
            picked = random.choice(self.cards)
            self.cards.remove(picked)
            return picked

    def __len__(self):
        return len(self.cards)

