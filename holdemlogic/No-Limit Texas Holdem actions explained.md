# ■ No-Limit 텍사스 홀덤: 각 행동의 가능 목록

## 액션 트리
```
[My Turn]
├── to_call == 0
│   ├── chips == 0
│   │   └── [Leaf] 자동 check (이미 올인)
│   ├── chips < min_bet
│   │   ├── [Leaf] check
│   │   └── [Leaf] all-in-bet (dead raise)
│   └── chips ≥ min_bet
│       ├── [Leaf] check
│       ├── [Leaf] bet (full raise)
│       └── [Leaf] all-in-bet (full raise)
│
└── to_call > 0
    ├── chips < to_call
    │   ├── [Leaf] fold
    │   └── [Leaf] all-in-call
    ├── to_call ≤ chips < to_call + min_raise_by
    │   ├── [Leaf] fold
    │   ├── [Leaf] call
    │   └── [Leaf] all-in-raise (dead raise)
    └── chips ≥ to_call + min_raise_by
        ├── [Leaf] fold
        ├── [Leaf] call
        ├── [Leaf] raise (full raise)
        └── [Leaf] all-in-raise (full raise)
```


## 
- **dead raise**는 **최소 인상 미달 raise**로, 다음 플레이어가 다시 raise할 수 없다.
- **full raise**는 최소 인상폭 이상을 만족하며, 다음 레이즈 허용 조건이 된다.
- all-in도 raise 값이 충분하면 **full raise**로 가능.

