from sortedcontainers import SortedList

game_registry = {} # dict[game_id] -> GameMananger
timeouts = SortedList(key=lambda gm: gm.deadline)
deadline = {}